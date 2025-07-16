"""
Модуль для получения актуального баланса через веб-интерфейс Polymarket
Безопасно работает с credentials через переменные окружения
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from loguru import logger

import aiohttp
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.config.settings import config


class PolymarketWebScraper:
    """Класс для получения баланса через веб-интерфейс Polymarket"""

    def __init__(self):
        self.session = None
        self.last_login = None
        self.session_lifetime = timedelta(hours=2)  # Сессия живет 2 часа
        self.cookies = {}
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9,ru;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin'
        }
        
    def _get_credentials(self) -> Tuple[Optional[str], Optional[str]]:
        """
        Безопасно получает credentials из переменных окружения
        Возвращает: (email, password) или (None, None)
        """
        try:
            # Credentials из переменных окружения (НЕ хранятся в коде!)
            email = config.polymarket.POLYMARKET_EMAIL if hasattr(config.polymarket, 'POLYMARKET_EMAIL') else None
            password = config.polymarket.POLYMARKET_PASSWORD if hasattr(config.polymarket, 'POLYMARKET_PASSWORD') else None
            
            if not email or not password:
                logger.warning("POLYMARKET_EMAIL или POLYMARKET_PASSWORD не настроены в переменных окружения")
                return None, None
                
            # Дополнительная проверка что это не тестовые значения
            if email in ["test@example.com", "your_email@example.com"] or password in ["password", "your_password"]:
                logger.warning("Обнаружены тестовые credentials, используйте реальные данные")
                return None, None
                
            logger.debug(f"Получены credentials для {email[:3]}***@{email.split('@')[1] if '@' in email else 'unknown'}")
            return email, password
            
        except Exception as e:
            logger.error(f"Ошибка получения credentials: {e}")
            return None, None

    def _create_session(self) -> requests.Session:
        """Создает настроенную HTTP сессию с retry logic"""
        session = requests.Session()
        
        # Настройка retry стратегии
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"]
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        # Устанавливаем headers
        session.headers.update(self.headers)
        
        return session

    async def _login_if_needed(self) -> bool:
        """
        Проверяет и выполняет login если нужно
        Возвращает True если сессия готова, False если ошибка
        """
        try:
            # Проверяем нужен ли login
            if (self.session and self.last_login and 
                datetime.now() - self.last_login < self.session_lifetime):
                logger.debug("Сессия еще активна, login не требуется")
                return True
            
            # Получаем credentials
            email, password = self._get_credentials()
            if not email or not password:
                logger.error("Не удалось получить credentials для входа")
                return False
            
            logger.info(f"Выполняется вход в Polymarket для {email[:3]}***@{email.split('@')[1]}")
            
            # Создаем новую сессию
            if self.session:
                self.session.close()
            self.session = self._create_session()
            
            # Шаг 1: Получаем главную страницу для cookies
            main_response = self.session.get('https://polymarket.com', timeout=15)
            if main_response.status_code != 200:
                logger.error(f"Ошибка загрузки главной страницы: {main_response.status_code}")
                return False
                
            logger.debug("✅ Главная страница загружена")
            
            # Шаг 2: Пробуем разные методы аутентификации
            login_success = await self._try_login_methods(email, password)
            
            if login_success:
                self.last_login = datetime.now()
                logger.info(f"✅ Успешный вход в Polymarket ({email[:3]}***@{email.split('@')[1]})")
                return True
            else:
                logger.error("❌ Не удалось войти в Polymarket")
                return False
                
        except Exception as e:
            logger.error(f"Ошибка при входе в Polymarket: {e}")
            return False

    async def _try_login_methods(self, email: str, password: str) -> bool:
        """Пробует разные методы входа в Polymarket"""
        
        # Метод 1: Magic Link / Email login (наиболее вероятный)
        if await self._try_magic_link_login(email):
            return True
            
        # Метод 2: Стандартный email/password login
        if await self._try_email_password_login(email, password):
            return True
            
        # Метод 3: OAuth/Social login detection
        if await self._try_social_login_detection():
            return True
            
        return False

    async def _try_magic_link_login(self, email: str) -> bool:
        """Пробует войти через Magic Link"""
        try:
            logger.info("🔗 Попытка входа через Magic Link")
            
            # Ищем API endpoint для Magic Link
            magic_endpoints = [
                'https://polymarket.com/api/auth/magic-link',
                'https://auth.magic.link/v1/login',
                'https://polymarket.com/auth/email'
            ]
            
            for endpoint in magic_endpoints:
                try:
                    response = self.session.post(
                        endpoint,
                        json={'email': email},
                        timeout=10
                    )
                    
                    if response.status_code in [200, 202]:
                        logger.info(f"✅ Magic Link запрос отправлен на {endpoint}")
                        logger.warning("⚠️ Требуется переход по ссылке из email!")
                        logger.warning("   После перехода по ссылке в email, сессия будет активна")
                        
                        # Даем время на переход по ссылке
                        await asyncio.sleep(30)
                        
                        # Проверяем установилась ли сессия
                        if await self._check_session_validity():
                            return True
                            
                except Exception as e:
                    logger.debug(f"Magic Link endpoint {endpoint} не работает: {e}")
                    continue
                    
            return False
            
        except Exception as e:
            logger.error(f"Ошибка Magic Link входа: {e}")
            return False

    async def _try_email_password_login(self, email: str, password: str) -> bool:
        """Пробует стандартный email/password вход"""
        try:
            logger.info("🔑 Попытка стандартного email/password входа")
            
            login_endpoints = [
                'https://polymarket.com/api/auth/login',
                'https://polymarket.com/auth/login',
                'https://api.polymarket.com/auth/login'
            ]
            
            login_data = {
                'email': email,
                'password': password
            }
            
            for endpoint in login_endpoints:
                try:
                    response = self.session.post(
                        endpoint,
                        json=login_data,
                        timeout=10
                    )
                    
                    if response.status_code == 200:
                        logger.info(f"✅ Успешный вход через {endpoint}")
                        return True
                    elif response.status_code == 401:
                        logger.warning(f"❌ Неверные credentials для {endpoint}")
                    else:
                        logger.debug(f"Login endpoint {endpoint} вернул {response.status_code}")
                        
                except Exception as e:
                    logger.debug(f"Login endpoint {endpoint} не работает: {e}")
                    continue
                    
            return False
            
        except Exception as e:
            logger.error(f"Ошибка email/password входа: {e}")
            return False

    async def _try_social_login_detection(self) -> bool:
        """Определяет доступные методы социального входа"""
        try:
            logger.info("🔍 Проверка методов социального входа")
            
            # Проверяем страницу входа на наличие социальных кнопок
            login_page = self.session.get('https://polymarket.com/login', timeout=10)
            if login_page.status_code == 200:
                content = login_page.text.lower()
                
                social_methods = []
                if 'google' in content:
                    social_methods.append('Google')
                if 'github' in content:
                    social_methods.append('GitHub')
                if 'discord' in content:
                    social_methods.append('Discord')
                if 'metamask' in content or 'wallet' in content:
                    social_methods.append('MetaMask/Wallet')
                    
                if social_methods:
                    logger.info(f"🔗 Обнаружены методы входа: {', '.join(social_methods)}")
                    logger.warning("⚠️ Для автоматизации социального входа нужна дополнительная настройка")
                    
            return False
            
        except Exception as e:
            logger.error(f"Ошибка определения социального входа: {e}")
            return False

    async def _check_session_validity(self) -> bool:
        """Проверяет валидность текущей сессии"""
        try:
            # Пробуем получить данные профиля
            profile_endpoints = [
                'https://polymarket.com/api/user/profile',
                'https://polymarket.com/api/auth/me',
                'https://polymarket.com/portfolio'
            ]
            
            for endpoint in profile_endpoints:
                try:
                    response = self.session.get(endpoint, timeout=10)
                    if response.status_code == 200:
                        logger.debug(f"✅ Сессия валидна (проверка через {endpoint})")
                        return True
                except:
                    continue
                    
            return False
            
        except Exception as e:
            logger.error(f"Ошибка проверки сессии: {e}")
            return False

    async def get_balance_from_web(self) -> Optional[Dict[str, float]]:
        """
        Основной метод получения баланса через веб-интерфейс
        Возвращает: {'balance': float, 'profit_loss': float} или None
        """
        try:
            logger.info("💰 Получение баланса через веб-интерфейс Polymarket")
            
            # Проверяем и выполняем login если нужно
            if not await self._login_if_needed():
                logger.error("Не удалось войти в систему")
                return None
            
            # Получаем данные с portfolio страницы
            balance_data = await self._fetch_portfolio_data()
            if balance_data:
                logger.info(f"✅ Баланс получен: ${balance_data.get('balance', 0):.2f}")
                return balance_data
            
            # Fallback: пробуем API endpoints
            api_balance = await self._fetch_balance_via_api()
            if api_balance:
                logger.info(f"✅ Баланс получен через API: ${api_balance.get('balance', 0):.2f}")
                return api_balance
                
            logger.warning("❌ Не удалось получить баланс ни одним способом")
            return None
            
        except Exception as e:
            logger.error(f"Ошибка получения баланса через веб: {e}")
            return None

    async def _fetch_portfolio_data(self) -> Optional[Dict[str, float]]:
        """Получает данные с portfolio страницы"""
        try:
            logger.debug("📊 Загрузка portfolio страницы")
            
            # Загружаем portfolio страницу
            portfolio_response = self.session.get(
                'https://polymarket.com/portfolio',
                timeout=15
            )
            
            if portfolio_response.status_code != 200:
                logger.warning(f"Portfolio страница недоступна: {portfolio_response.status_code}")
                return None
            
            content = portfolio_response.text
            
            # Ищем данные в HTML/JavaScript
            balance_data = self._parse_portfolio_html(content)
            if balance_data:
                return balance_data
            
            # Ищем AJAX вызовы в Network tab
            ajax_data = await self._fetch_portfolio_ajax()
            if ajax_data:
                return ajax_data
                
            return None
            
        except Exception as e:
            logger.error(f"Ошибка загрузки portfolio: {e}")
            return None

    def _parse_portfolio_html(self, html_content: str) -> Optional[Dict[str, float]]:
        """Парсит баланс из HTML content portfolio страницы"""
        try:
            import re
            
            # Ищем паттерны для баланса
            balance_patterns = [
                r'portfolio["\s]*:[\s]*["$]?([\d,]+\.?\d*)',
                r'balance["\s]*:[\s]*["$]?([\d,]+\.?\d*)',
                r'cash["\s]*:[\s]*["$]?([\d,]+\.?\d*)',
                r'\$?([\d,]+\.?\d*)\s*</.*>.*portfolio',
                r'value["\s]*:[\s]*["$]?([\d,]+\.?\d*)'
            ]
            
            # Ищем паттерны для P&L
            pnl_patterns = [
                r'profit["\s]*:[\s]*[-$]?([\d,]+\.?\d*)',
                r'loss["\s]*:[\s]*[-$]?([\d,]+\.?\d*)',
                r'pnl["\s]*:[\s]*[-$]?([\d,]+\.?\d*)',
                r'[-]?\$?([\d,]+\.?\d*)\s*</.*>.*profit'
            ]
            
            balance = None
            profit_loss = None
            
            # Ищем баланс
            for pattern in balance_patterns:
                match = re.search(pattern, html_content, re.IGNORECASE)
                if match:
                    balance_str = match.group(1).replace(',', '')
                    try:
                        balance = float(balance_str)
                        logger.debug(f"Найден баланс в HTML: ${balance}")
                        break
                    except ValueError:
                        continue
            
            # Ищем P&L
            for pattern in pnl_patterns:
                match = re.search(pattern, html_content, re.IGNORECASE)
                if match:
                    pnl_str = match.group(1).replace(',', '')
                    try:
                        profit_loss = float(pnl_str)
                        # Определяем знак по контексту
                        if 'loss' in match.group(0).lower() or '-' in match.group(0):
                            profit_loss = -abs(profit_loss)
                        logger.debug(f"Найден P&L в HTML: {profit_loss}")
                        break
                    except ValueError:
                        continue
            
            if balance is not None:
                return {
                    'balance': balance,
                    'profit_loss': profit_loss or 0.0,
                    'source': 'html_parsing'
                }
                
            return None
            
        except Exception as e:
            logger.error(f"Ошибка парсинга HTML: {e}")
            return None

    async def _fetch_portfolio_ajax(self) -> Optional[Dict[str, float]]:
        """Пробует найти AJAX endpoints для portfolio данных"""
        try:
            logger.debug("🔍 Поиск AJAX endpoints для portfolio")
            
            # Список вероятных API endpoints
            api_endpoints = [
                'https://polymarket.com/api/portfolio',
                'https://polymarket.com/api/user/balance',
                'https://polymarket.com/api/wallet/balance',
                'https://api.polymarket.com/portfolio',
                'https://data-api.polymarket.com/portfolio',
                'https://polymarket.com/api/positions/summary'
            ]
            
            for endpoint in api_endpoints:
                try:
                    response = self.session.get(endpoint, timeout=10)
                    if response.status_code == 200:
                        data = response.json()
                        logger.debug(f"✅ Получены данные от {endpoint}")
                        
                        # Парсим ответ
                        balance_data = self._parse_api_response(data, endpoint)
                        if balance_data:
                            return balance_data
                            
                except Exception as e:
                    logger.debug(f"AJAX endpoint {endpoint} не работает: {e}")
                    continue
                    
            return None
            
        except Exception as e:
            logger.error(f"Ошибка AJAX запросов: {e}")
            return None

    def _parse_api_response(self, data: Dict, endpoint: str) -> Optional[Dict[str, float]]:
        """Парсит ответ API для извлечения баланса"""
        try:
            balance = None
            profit_loss = None
            
            # Различные структуры ответа
            if isinstance(data, dict):
                # Прямые поля
                balance = data.get('balance') or data.get('total') or data.get('value')
                profit_loss = data.get('pnl') or data.get('profit_loss') or data.get('profit')
                
                # Вложенные объекты
                if not balance and 'portfolio' in data:
                    portfolio = data['portfolio']
                    balance = portfolio.get('balance') or portfolio.get('total')
                    profit_loss = portfolio.get('pnl') or portfolio.get('profit_loss')
                
                # Массивы позиций
                if not balance and 'positions' in data:
                    positions = data['positions']
                    if isinstance(positions, list):
                        total_value = sum(pos.get('value', 0) for pos in positions)
                        if total_value > 0:
                            balance = total_value
            
            if balance is not None:
                logger.debug(f"Баланс извлечен из API {endpoint}: ${balance}")
                return {
                    'balance': float(balance),
                    'profit_loss': float(profit_loss) if profit_loss else 0.0,
                    'source': f'api_{endpoint.split("/")[-1]}'
                }
                
            return None
            
        except Exception as e:
            logger.error(f"Ошибка парсинга API ответа: {e}")
            return None

    async def _fetch_balance_via_api(self) -> Optional[Dict[str, float]]:
        """Fallback метод через прямые API вызовы"""
        try:
            logger.debug("🔄 Fallback: прямые API вызовы")
            
            # Получаем user ID или address
            user_data = await self._get_user_data()
            if not user_data:
                return None
            
            user_id = user_data.get('id') or user_data.get('address')
            if not user_id:
                return None
            
            # Используем существующий PolymarketClient для получения баланса
            from src.polymarket_client import PolymarketClient
            client = PolymarketClient()
            
            api_balance = client.get_account_balance()
            if api_balance and api_balance > 0:
                return {
                    'balance': api_balance,
                    'profit_loss': 0.0,  # P&L через API не доступен
                    'source': 'polymarket_api'
                }
                
            return None
            
        except Exception as e:
            logger.error(f"Ошибка API fallback: {e}")
            return None

    async def _get_user_data(self) -> Optional[Dict]:
        """Получает данные пользователя"""
        try:
            user_endpoints = [
                'https://polymarket.com/api/user',
                'https://polymarket.com/api/auth/me',
                'https://polymarket.com/api/profile'
            ]
            
            for endpoint in user_endpoints:
                try:
                    response = self.session.get(endpoint, timeout=10)
                    if response.status_code == 200:
                        return response.json()
                except:
                    continue
                    
            return None
            
        except Exception as e:
            logger.error(f"Ошибка получения user data: {e}")
            return None

    async def close(self):
        """Закрывает сессию"""
        if self.session:
            self.session.close()
            self.session = None
            logger.debug("WebScraper сессия закрыта")


# Глобальный экземпляр скрапера
web_scraper = PolymarketWebScraper() 