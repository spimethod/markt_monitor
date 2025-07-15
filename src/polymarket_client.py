"""
Асинхронный клиент для взаимодействия с Polymarket API и смарт-контрактами
"""
import asyncio
import binascii
import json
import threading
import random
from typing import Dict, Optional, Any, Tuple
from datetime import datetime

import requests
import websockets
from eth_account.signers.local import LocalAccount
from loguru import logger
from web3 import Account
from websockets.client import WebSocketClientProtocol

from src.config.settings import Config
from src.database.manager import DatabaseManager

# Создаем экземпляр конфига, чтобы он был доступен глобально
# Это безопасно, так как модуль импортируется один раз
config_instance = Config()

async def default_message_handler(message: Dict[str, Any]):
    """Обработчик сообщений по умолчанию. Просто логирует сообщение."""
    logger.info(f"Получено сообщение WebSocket: {message}")


class PolymarketClient:
    """Асинхронный клиент для взаимодействия с Polymarket API и смарт-контрактами"""

    def __init__(self, message_handler=default_message_handler):
        """Инициализация клиента"""
        self.config: Config = config_instance
        self.db_manager = DatabaseManager()
        self.account: Optional[LocalAccount] = None
        self.is_connected = False
        self.websocket: Optional[WebSocketClientProtocol] = None
        self.ws_thread: Optional[threading.Thread] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.message_handler = message_handler
        self.is_running = True

        if self.config.polymarket.PRIVATE_KEY:
            try:
                self.account = Account.from_key(self.config.polymarket.PRIVATE_KEY)
                if self.account:
                    logger.info(f"Аккаунт {self.account.address} успешно инициализирован.")
            except (ValueError, binascii.Error) as e:
                logger.error(f"Ошибка инициализации аккаунта: {e}. Проверьте PRIVATE_KEY.")
        else:
            logger.warning("PRIVATE_KEY не установлен. Торговля будет недоступна.")

        if self.config.polymarket.USE_WEBSOCKET:
            logger.info("Запуск стабильного WebSocket с автоматическим переподключением")
            self._start_websocket_listener()

    def get_address(self) -> Optional[str]:
        """Возвращает адрес аккаунта, если он доступен."""
        return self.account.address if self.account else None

    async def place_order(self, token_id: str, side: str, size: float, price: float, market_data: Optional[Dict] = None) -> Optional[Dict]:
        """
        Размещает ордер на покупку или продажу и сохраняет позицию в БД.
        """
        if not self.account:
            logger.error("Невозможно разместить ордер: приватный ключ не установлен.")
            return None
            
        logger.info(f"Размещение ордера: {side} {size} токенов {token_id} по цене {price}")
        
        # Генерируем уникальный ID для ордера
        import uuid
        order_id = f"order_{int(datetime.now().timestamp())}_{str(uuid.uuid4())[:8]}"
        
        # Здесь будет логика для реального размещения ордера
        order_data = {
            "token_id": token_id, "price": str(price), "size": str(size),
            "side": side, "status": "placed", "id": order_id
        }
        
        # Сохраняем позицию в базу данных
        try:
            market_id = None
            market_name = None
            if market_data:
                market_id = market_data.get("question_id") or market_data.get("condition_id") or market_data.get("market_slug")
                market_name = market_data.get("question", "Неизвестный рынок")[:500]  # Ограничиваем размер
            
            position_data = {
                "id": order_id,
                "token_id": token_id,
                "market_id": market_id,
                "user_address": self.account.address,
                "side": side,
                "size": size,
                "entry_price": price,
                "current_price": price,
                "target_profit": self.config.trading.PROFIT_TARGET_PERCENT,
                "stop_loss": self.config.trading.STOP_LOSS_PERCENT,
                "status": "open",
                "market_name": market_name
            }
            
            # Асинхронно сохраняем в БД
            save_success = await self.db_manager.save_position(position_data)
            if save_success:
                logger.info(f"✅ Позиция {order_id} сохранена в БД")
            else:
                logger.warning(f"⚠️ Не удалось сохранить позицию {order_id} в БД")
                
        except Exception as e:
            logger.error(f"Ошибка сохранения позиции в БД: {e}")
        
        return order_data

    def get_markets(self) -> list:
        """Получает список активных рынков"""
        try:
            url = "https://clob.polymarket.com/markets"
            logger.info(f"🔗 Запрос рынков: {url}")
            
            response = self._make_request("GET", url)
            
            if not response:
                logger.warning("❌ Polymarket API не вернул данные")
                return []
                
            logger.info(f"✅ Получен ответ от Polymarket API")
            logger.info(f"📊 Тип ответа: {type(response)}")
            logger.info(f"📊 Статус код: {response.status_code}")
            
            # Получаем JSON из Response объекта
            try:
                data = response.json()
                logger.info(f"📋 JSON данные получены, тип: {type(data)}")
            except Exception as e:
                logger.error(f"❌ Ошибка парсинга JSON: {e}")
                logger.info(f"📄 Содержимое ответа: {response.text[:500]}")
                return []
            
            if isinstance(data, dict):
                # Если ответ - словарь, ищем список в нем
                if 'data' in data:
                    markets = data['data']
                    logger.info(f"📋 Найдены рынки в data['data']: {len(markets)} штук")
                elif 'markets' in data:
                    markets = data['markets']  
                    logger.info(f"📋 Найдены рынки в data['markets']: {len(markets)} штук")
                else:
                    logger.warning(f"⚠️  Неожиданная структура ответа: {list(data.keys())}")
                    logger.info(f"📄 Структура JSON: {data}")
                    return []
            elif isinstance(data, list):
                markets = data
                logger.info(f"📋 Получен прямой список рынков: {len(markets)} штук")
            else:
                logger.warning(f"❌ Неожиданный тип JSON данных: {type(data)}")
                return []
            
            # Логируем детали первых 3 рынков
            for i, market in enumerate(markets[:3]):
                if isinstance(market, dict):
                    logger.info(f"🎯 Рынок #{i+1}:")
                    logger.info(f"   📋 Вопрос: {market.get('question', 'N/A')}")
                    
                    # Используем правильные поля из API
                    market_id = market.get('question_id') or market.get('condition_id') or market.get('market_slug', 'N/A')
                    logger.info(f"   🆔 ID: {market_id}")
                    
                    # Polymarket API не возвращает прямые поля liquidity/volume в этом эндпоинте
                    # Показываем другую полезную информацию
                    logger.info(f"   🎮 Активен: {market.get('active', False)}")
                    logger.info(f"   🔒 Закрыт: {market.get('closed', False)}")
                    logger.info(f"   💱 Принимает ордера: {market.get('accepting_orders', False)}")
                    
                    # Считаем количество исходов из tokens
                    tokens = market.get('tokens', [])
                    outcomes = market.get('outcomes', [])
                    total_outcomes = len(tokens) if tokens else len(outcomes)
                    logger.info(f"   🎲 Исходы: {total_outcomes}")
                    
                    # Показываем детали токенов
                    if tokens:
                        for j, token in enumerate(tokens[:2]):  # Показываем первые 2
                            if isinstance(token, dict):
                                outcome_name = token.get('outcome', f'Исход {j+1}')
                                price = token.get('price', 'N/A')
                                logger.info(f"     🎯 {outcome_name}: цена {price}")
                    
                    # Время
                    end_date = market.get('end_date_iso') or market.get('game_start_time', 'N/A')
                    logger.info(f"   📅 Дата завершения: {end_date}")
                    
                    # ПОЛНАЯ СТРУКТУРА первого рынка для отладки
                    if i == 0:
                        logger.info(f"🔍 ПОЛНАЯ СТРУКТУРА РЫНКА #1:")
                        for key, value in market.items():
                            value_str = str(value)[:100] + "..." if len(str(value)) > 100 else str(value)
                            logger.info(f"     {key}: {value_str}")
                    
                    # Детали исходов - оставляем для совместимости, но токены важнее
                    outcomes = market.get('outcomes', [])
                    for j, outcome in enumerate(outcomes):
                        if isinstance(outcome, dict):
                            logger.info(f"     Исход {j+1}: {outcome.get('name', 'N/A')} (asset_id: {outcome.get('asset_id', 'N/A')})")
                else:
                    logger.warning(f"⚠️  Рынок #{i+1} не является словарем: {type(market)}")
            
            # ПРИНУДИТЕЛЬНОЕ логирование структуры
            if markets and len(markets) > 0:
                first_market = markets[0]
                if isinstance(first_market, dict):
                    logger.info("=" * 50)
                    logger.info("🔍 ДЕТАЛЬНАЯ СТРУКТУРА ПЕРВОГО РЫНКА:")
                    logger.info(f"Тип: {type(first_market)}")
                    logger.info(f"Количество ключей: {len(first_market.keys())}")
                    logger.info("Все ключи:")
                    for key in first_market.keys():
                        value = first_market[key]
                        value_str = str(value)[:100] + "..." if len(str(value)) > 100 else str(value)
                        logger.info(f"  {key} = {value_str}")
                    logger.info("=" * 50)
            
            logger.info(f"🎯 ИТОГО ПОЛУЧЕНО: {len(markets)} рынков от Polymarket")
            return markets
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения рынков: {e}")
            return []

    def get_current_price(self, token_id: str) -> Optional[float]:
        """Получение текущей цены токена"""
        # Эта функция требует реальной реализации
        logger.warning("Функция get_current_price не реализована и возвращает моковое значение.")
        return 0.5

    def get_account_balance(self) -> float:
        """
        Получение баланса аккаунта через Polymarket Data API с fallback на RPC
        """
        try:
            logger.info("💰 Получение баланса через Polymarket Data API")
            
            # Список адресов для проверки
            addresses_to_check = []
            
            # Добавляем proxy адрес если он настроен
            if self.config.polymarket.POLYMARKET_PROXY_ADDRESS:
                addresses_to_check.append(self.config.polymarket.POLYMARKET_PROXY_ADDRESS)
            
            # Добавляем main адрес
            main_address = self.get_address()
            if main_address:
                addresses_to_check.append(main_address)
            
            logger.info(f"🔍 Проверяем {len(addresses_to_check)} адресов")
            for i, addr in enumerate(addresses_to_check):
                addr_type = "PROXY" if i == 0 and self.config.polymarket.POLYMARKET_PROXY_ADDRESS else "MAIN"
                logger.info(f"   📍 {addr_type}: {addr}")
            
            for user_address in addresses_to_check:
                logger.info(f"🔍 Проверка баланса для {['PROXY', 'MAIN'][addresses_to_check.index(user_address)]} адреса: {user_address}")
                
                # Пробуем получить общую стоимость позиций
                positions_value = self._get_positions_value(user_address)
                
                # Пробуем получить свободный USDC
                proxy_wallet, free_usdc = self._get_free_usdc_balance(user_address)
                
                # Пробуем прямую проверку USDC баланса на самом адресе
                direct_usdc = self._check_usdc_balance_for_address(user_address)
                
                logger.info(f"📊 Общая стоимость позиций: ${positions_value or 0:.6f}")
                if free_usdc is not None:
                    logger.info(f"💵 Свободный USDC (proxy): ${free_usdc:.6f}")
                if direct_usdc is not None:
                    logger.info(f"💵 Прямой USDC (сам адрес): ${direct_usdc:.6f}")
                
                # Рассчитываем общий баланс
                total_balance = 0.0
                
                if positions_value and positions_value > 0:
                    total_balance += positions_value
                
                if free_usdc and free_usdc > 0:
                    total_balance += free_usdc
                elif direct_usdc and direct_usdc > 0:
                    total_balance += direct_usdc
                
                if total_balance > 0:
                    logger.info(f"✅ Найден баланс ${total_balance:.6f} на адресе {user_address}")
                    return total_balance
            
            # Fallback на старые методы
            logger.info("🔄 Переход на fallback методы получения баланса")
            return self._get_balance_fallback()
            
        except Exception as e:
            logger.error(f"Ошибка получения баланса: {e}")
            return 0.0

    def _get_positions_value(self, user_address: str) -> Optional[float]:
        """Получение общей USD стоимости всех позиций через Polymarket Data API"""
        try:
            # Валидация адреса
            if len(user_address) != 42 or not user_address.startswith("0x"):
                logger.warning(f"⚠️ Некорректный формат адреса: {user_address} (длина: {len(user_address)}, ожидается 42)")
                return None
            
            # API endpoint для получения общей стоимости позиций
            value_url = f"https://data-api.polymarket.com/value?user={user_address}"
            logger.debug(f"📡 Запрос к Data API (value): {value_url}")
            
            response = requests.get(value_url, timeout=10)
            logger.debug(f"📊 Data API (value) статус: {response.status_code}")
            
            if response.status_code == 400:
                logger.warning(f"⚠️ Data API (value) вернул 400: возможно некорректный адрес {user_address}")
                return None
            elif response.status_code == 200:
                data = response.json()
                logger.debug(f"📋 Data API (value) ответ: {data}")
                
                if isinstance(data, list) and len(data) > 0:
                    user_data = data[0]  # Берем первый элемент
                    if isinstance(user_data, dict) and 'value' in user_data:
                        total_value = float(user_data['value'])
                        logger.info(f"✅ Получена общая стоимость позиций: ${total_value:.6f}")
                        return total_value
                    else:
                        logger.warning("⚠️ Data API (value): неожиданная структура ответа")
                elif isinstance(data, list) and len(data) == 0:
                    logger.info("ℹ️ Data API (value): позиции не найдены")
                    return 0.0
                else:
                    logger.warning(f"⚠️ Data API (value): неожиданный тип данных: {type(data)}")
            else:
                logger.warning(f"⚠️ Data API (value) ошибка HTTP: {response.status_code}")
                
        except Exception as e:
            logger.warning(f"❌ Ошибка Data API (value): {e}")
            
        return None

    def _get_free_usdc_balance(self, user_address: str) -> Tuple[Optional[str], Optional[float]]:
        """
        Получение свободного USDC баланса через proxy wallet
        Возвращает: (proxy_wallet_address, free_usdc_balance)
        """
        try:
            # Валидация адреса
            if len(user_address) != 42 or not user_address.startswith("0x"):
                logger.warning(f"⚠️ Некорректный формат адреса: {user_address} (длина: {len(user_address)}, ожидается 42)")
                return None, None
            
            # API endpoint для получения детальных позиций
            positions_url = f"https://data-api.polymarket.com/positions?user={user_address}"
            logger.debug(f"📡 Запрос к Data API (positions): {positions_url}")
            
            response = requests.get(positions_url, timeout=10)
            logger.debug(f"📊 Data API (positions) статус: {response.status_code}")
            
            if response.status_code == 400:
                logger.warning(f"⚠️ Data API (positions) вернул 400: возможно некорректный адрес {user_address}")
                return None, None
            elif response.status_code == 200:
                data = response.json()
                logger.debug(f"📋 Data API (positions) ответ: {type(data)} с {len(data) if isinstance(data, list) else 'неизвестным'} элементами")
                
                proxy_wallet = None
                
                if isinstance(data, list) and len(data) > 0:
                    # Ищем proxy wallet в первой позиции
                    first_position = data[0]
                    if isinstance(first_position, dict) and 'proxyWallet' in first_position:
                        proxy_wallet = first_position['proxyWallet']
                        logger.info(f"🏦 Найден proxy wallet: {proxy_wallet}")
                        
                        # Теперь получаем свободный USDC баланс для proxy wallet
                        free_usdc = self._check_usdc_balance_for_address(proxy_wallet)
                        return proxy_wallet, free_usdc
                    else:
                        logger.warning("⚠️ Data API (positions): proxyWallet не найден в данных")
                elif isinstance(data, list) and len(data) == 0:
                    logger.info("ℹ️ Data API (positions): позиции не найдены")
                    return None, 0.0
                else:
                    logger.warning(f"⚠️ Data API (positions): неожиданный тип данных: {type(data)}")
            else:
                logger.warning(f"⚠️ Data API (positions) ошибка HTTP: {response.status_code}")
                
        except Exception as e:
            logger.warning(f"❌ Ошибка Data API (positions): {e}")
            
        return None, None

    def _check_usdc_balance_for_address(self, user_address: str) -> Optional[float]:
        """Проверяет свободный баланс USDC для конкретного адреса через RPC"""
        try:
            # USDC контракты на Polygon (приоритет нативному USDC)
            usdc_contracts = [
                ("Native USDC", "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"),  # Нативный USDC (приоритет)
                ("Bridged USDC", "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"),  # Bridged USDC
            ]
            
            # Обновленные RPC endpoints для Polygon
            rpc_endpoints = [
                "https://polygon-rpc.com",
                "https://polygon.llamarpc.com", 
                "https://rpc-mainnet.matic.network",
                "https://polygon.blockpi.network/v1/rpc/public",
            ]
            
            logger.debug(f"🔍 Проверка свободного USDC для адреса: {user_address}")
            
            for contract_name, contract_addr in usdc_contracts:
                logger.debug(f"📋 Проверка {contract_name}: {contract_addr}")
                
                # Формируем данные для вызова balanceOf
                function_signature = "0x70a08231"  # balanceOf(address)
                padded_address = user_address.replace("0x", "").lower().zfill(64)
                call_data = function_signature + padded_address
                
                for rpc_url in rpc_endpoints:
                    try:
                        payload = {
                            "jsonrpc": "2.0",
                            "method": "eth_call",
                            "params": [{
                                "to": contract_addr,
                                "data": call_data
                            }, "latest"],
                            "id": 1
                        }
                        
                        response = requests.post(
                            rpc_url,
                            json=payload,
                            headers={"Content-Type": "application/json"},
                            timeout=10
                        )
                        
                        if response.status_code != 200:
                            logger.debug(f"⚠️ RPC {rpc_url} вернул статус {response.status_code}")
                            continue
                            
                        data = response.json()
                        result = data.get("result", "0x0")
                        
                        if result and result != "0x0" and not result.endswith("0" * 60):
                            # Конвертируем из hex в decimal (USDC имеет 6 decimals)
                            balance_wei = int(result, 16)
                            balance_usdc = balance_wei / (10 ** 6)  # USDC имеет 6 знаков после запятой
                            
                            if balance_usdc > 0:
                                logger.info(f"✅ Найден свободный USDC: ${balance_usdc:.6f} ({contract_name})")
                                logger.info(f"   🏦 Адрес: {user_address}")
                                logger.info(f"   📄 Контракт: {contract_addr}")
                                logger.info(f"   🌐 RPC: {rpc_url}")
                                return balance_usdc
                                
                    except Exception as e:
                        logger.debug(f"❌ Ошибка с RPC {rpc_url}: {e}")
                        continue
                        
            logger.debug(f"ℹ️ Свободный USDC не найден для адреса {user_address}")
            return 0.0
            
        except Exception as e:
            logger.error(f"Ошибка проверки баланса для {user_address}: {e}")
            return None

    def _get_balance_fallback(self) -> float:
        """Fallback методы для получения баланса"""
        try:
            # Пробуем проверить баланс напрямую для всех адресов
            addresses_to_try = []
            
            # Main адрес
            if self.account:
                addresses_to_try.append(self.account.address)
            
            # Proxy адрес
            if self.config.polymarket.POLYMARKET_PROXY_ADDRESS:
                addresses_to_try.append(self.config.polymarket.POLYMARKET_PROXY_ADDRESS)
            
            logger.info(f"🔄 Fallback: проверяем прямой USDC баланс для {len(addresses_to_try)} адресов")
            
            for addr in addresses_to_try:
                usdc_balance = self._check_usdc_balance_for_address(addr)
                if usdc_balance and usdc_balance > 0:
                    logger.info(f"✅ Fallback: найден USDC ${usdc_balance:.6f} на {addr}")
                    return usdc_balance
            
            logger.warning("⚠️ Fallback: баланс не найден ни на одном адресе")
            return 0.0
            
        except Exception as e:
            logger.error(f"Ошибка fallback получения баланса: {e}")
            return 0.0

    async def monitor_balance(self):
        """Мониторинг баланса с уведомлениями о критических изменениях"""
        if not self.account:
            return
        
        try:
            current_balance = self.get_account_balance()
            if current_balance is None:
                logger.warning("Не удалось получить баланс для мониторинга")
                return
            
            # Сохраняем предыдущий баланс для сравнения
            if not hasattr(self, '_previous_balance'):
                self._previous_balance = current_balance
                logger.info(f"Инициализация мониторинга баланса: ${current_balance:.2f}")
                return
            
            # Проверяем значительные изменения баланса (больше 5%)
            balance_change = current_balance - self._previous_balance
            change_percent = abs(balance_change) / self._previous_balance * 100 if self._previous_balance > 0 else 0
            
            if change_percent >= 5.0:  # Изменение более чем на 5%
                from src.telegram_bot import telegram_notifier
                
                change_emoji = "📈" if balance_change > 0 else "📉"
                await telegram_notifier.send_message(
                    f"{change_emoji} <b>Значительное изменение баланса</b>\n\n"
                    f"💰 <b>Было:</b> ${self._previous_balance:.2f}\n"
                    f"💰 <b>Стало:</b> ${current_balance:.2f}\n"
                    f"📊 <b>Изменение:</b> {balance_change:+.2f} ({change_percent:+.1f}%)\n\n"
                    f"⏰ <i>{datetime.now().strftime('%H:%M:%S')} UTC</i>"
                )
                logger.info(f"Отправлено уведомление об изменении баланса: {balance_change:+.2f} ({change_percent:+.1f}%)")
            
            # Проверяем критически низкий баланс (меньше $5)
            if current_balance < 5.0:
                from src.telegram_bot import telegram_notifier
                await telegram_notifier.send_message(
                    f"🚨 <b>Критически низкий баланс!</b>\n\n"
                    f"💰 <b>Баланс:</b> ${current_balance:.2f}\n"
                    f"⚠️ <b>Рекомендация:</b> Пополните баланс для продолжения торговли\n\n"
                    f"⏰ <i>{datetime.now().strftime('%H:%M:%S')} UTC</i>"
                )
                logger.warning(f"Критически низкий баланс: ${current_balance:.2f}")
            
            self._previous_balance = current_balance
            logger.debug(f"Мониторинг баланса: ${current_balance:.2f}")
            
        except Exception as e:
            logger.error(f"Ошибка мониторинга баланса: {e}")

    async def check_balance(self, frequency_seconds: int):
        """Периодическая проверка баланса с расширенной аналитикой"""
        if not self.account:
            return
        
        try:
            current_balance = self.get_account_balance()
            if current_balance is None:
                return
            
            # Инициализируем статистику баланса при первом запуске
            if not hasattr(self, '_balance_stats'):
                self._balance_stats = {
                    'initial_balance': current_balance,
                    'max_balance': current_balance,
                    'min_balance': current_balance,
                    'check_count': 0,
                    'last_check': datetime.now()
                }
                logger.info(f"Инициализация статистики баланса: ${current_balance:.2f}")
                return
            
            # Обновляем статистику
            stats = self._balance_stats
            stats['check_count'] += 1
            stats['max_balance'] = max(stats['max_balance'], current_balance)
            stats['min_balance'] = min(stats['min_balance'], current_balance)
            stats['last_check'] = datetime.now()
            
            # Рассчитываем нужное количество проверок для интервала сводки
            summary_interval_seconds = self.config.trading.BALANCE_SUMMARY_INTERVAL_MINUTES * 60
            checks_per_summary = max(1, summary_interval_seconds // frequency_seconds)
            
            # Каждые N проверок отправляем сводку (настраивается через BALANCE_SUMMARY_INTERVAL_MINUTES)
            if stats['check_count'] % checks_per_summary == 0:
                from src.telegram_bot import telegram_notifier
                
                total_change = current_balance - stats['initial_balance']
                total_change_percent = (total_change / stats['initial_balance'] * 100) if stats['initial_balance'] > 0 else 0
                
                await telegram_notifier.send_message(
                    f"📊 <b>Сводка баланса</b>\n\n"
                    f"💰 <b>Текущий:</b> ${current_balance:.2f}\n"
                    f"🎯 <b>Начальный:</b> ${stats['initial_balance']:.2f}\n"
                    f"📈 <b>Максимум:</b> ${stats['max_balance']:.2f}\n"
                    f"📉 <b>Минимум:</b> ${stats['min_balance']:.2f}\n"
                    f"📊 <b>Общее изменение:</b> {total_change:+.2f} ({total_change_percent:+.1f}%)\n"
                    f"🔄 <b>Проверок:</b> {stats['check_count']}\n\n"
                    f"⏰ <i>{datetime.now().strftime('%H:%M:%S')} UTC</i>"
                )
                logger.info(f"Отправлена сводка баланса (проверка #{stats['check_count']}, интервал {self.config.trading.BALANCE_SUMMARY_INTERVAL_MINUTES} мин)")
            
            logger.debug(f"Проверка баланса #{stats['check_count']}: ${current_balance:.2f}")
            
        except Exception as e:
            logger.error(f"Ошибка проверки баланса: {e}")

    def _make_request(self, method, url, **kwargs) -> Optional[requests.Response]:
        """Отправляет HTTP запрос"""
        try:
            response = requests.request(method, url, timeout=10, **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            logger.error(f"Ошибка HTTP запроса к {url}: {e}")
            return None

    async def check_and_close_positions(self):
        """Проверяет и закрывает позиции в соответствии со стратегией."""
        if not self.account:
            return

        try:
            open_positions = await self.db_manager.get_open_positions()
            user_address = self.get_address()
            user_positions = [p for p in open_positions if p.get('user_address') == user_address]

            if not user_positions:
                logger.debug("Нет открытых позиций для проверки")
                return

            logger.debug(f"Проверка {len(user_positions)} открытых позиций")

            for position in user_positions:
                current_price = self.get_current_price(position['token_id'])
                if not current_price:
                    logger.warning(f"Не удалось получить цену для токена {position['token_id']}")
                    continue
                
                # Обновляем текущую цену в БД
                await self.db_manager.update_position_price(position['id'], current_price)
                
                entry_price = position['entry_price']
                pnl_percent = ((current_price - entry_price) / entry_price) * 100
                
                # Проверяем условия закрытия позиции
                should_close, reason = self._should_close_position(position, current_price, pnl_percent)
                
                if should_close:
                    # Закрываем позицию
                    await self._close_position(position, reason, pnl_percent)
                    
                    # Удаляем рынок из списка с активными позициями если это была последняя позиция
                    await self._cleanup_market_from_active_positions(position['market_id'])
                else:
                    logger.debug(f"Позиция {position['id']}: PnL {pnl_percent:.2f}%, цена ${current_price:.4f}")

        except Exception as e:
            logger.error(f"Ошибка при проверке и закрытии позиций: {e}")

    def _should_close_position(self, position: Dict, current_price: float, pnl_percent: float) -> Tuple[bool, str]:
        """Определяет, нужно ли закрыть позицию"""
        
        # Проверка на прибыль
        target_profit = position.get('target_profit', self.config.trading.PROFIT_TARGET_PERCENT)
        if pnl_percent >= target_profit:
            return True, f"Достигнута целевая прибыль {target_profit:.1f}%"
        
        # Проверка на стоп-лосс
        stop_loss = position.get('stop_loss', self.config.trading.STOP_LOSS_PERCENT)
        if pnl_percent <= stop_loss:
            return True, f"Сработал стоп-лосс {stop_loss:.1f}%"
        
        # Проверка на время
        created_at = datetime.fromisoformat(position['created_at'].replace('Z', '+00:00'))
        hours_open = (datetime.utcnow().replace(tzinfo=created_at.tzinfo) - created_at).total_seconds() / 3600
        max_hours = self.config.trading.MAX_POSITION_HOURS
        
        if hours_open >= max_hours:
            return True, f"Превышено максимальное время удержания ({max_hours}ч)"
        
        return False, "Условия закрытия не выполнены"

    async def _close_position(self, position: Dict, reason: str, pnl_percent: float):
        """Закрывает позицию"""
        position_id = position['id']
        
        try:
            logger.info(f"🔴 Закрытие позиции {position_id}: {reason}")
            logger.info(f"📊 PnL: {pnl_percent:.2f}%")
            
            # Здесь будет логика реального закрытия позиции через API
            # Пока просто обновляем статус в БД
            
            pnl_amount = (position['size'] * position['entry_price']) * (pnl_percent / 100)
            
            await self.db_manager.close_position(position_id, reason, pnl_amount)
            
            # Отправляем уведомление в Telegram
            from src.telegram_bot import telegram_notifier
            await telegram_notifier.send_profit_notification({
                'order_id': position_id,
                'profit_percent': pnl_percent,
                'pnl_amount': pnl_amount,
                'reason': reason
            })
            
            logger.info(f"✅ Позиция {position_id} успешно закрыта")
            
        except Exception as e:
            logger.error(f"Ошибка закрытия позиции {position_id}: {e}")

    async def _cleanup_market_from_active_positions(self, market_id: Optional[str]):
        """Удаляет рынок из списка активных если нет открытых позиций"""
        if not market_id:
            return
            
        try:
            # Проверяем, есть ли еще открытые позиции для этого рынка
            open_positions = await self.db_manager.get_open_positions()
            user_address = self.get_address()
            market_positions = [p for p in open_positions 
                              if p.get('user_address') == user_address and p.get('market_id') == market_id]
            
            if not market_positions:
                # Нет больше позиций для этого рынка - удаляем из активных
                # Этот код будет вызван из торгового движка
                logger.info(f"🧹 Удаляем рынок {market_id} из списка активных (нет открытых позиций)")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Ошибка очистки рынка {market_id}: {e}")
            return False

    def _start_websocket_listener(self):
        """Запускает WebSocket слушатель в отдельном потоке с автоматическим переподключением."""
        self.ws_thread = threading.Thread(target=self._websocket_loop, daemon=True)
        self.ws_thread.start()

    def _websocket_loop(self):
        """Основной цикл для WebSocket соединения с автоматическим переподключением."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._stable_websocket_handler())
        self.loop.close()

    async def _stable_websocket_handler(self):
        """Стабильный обработчик WebSocket с автоматическим переподключением и fallback."""
        url = self.config.polymarket.WEBSOCKET_HOST + "/ws/market"
        connection_attempts = 0
        max_attempts = self.config.polymarket.WEBSOCKET_MAX_ATTEMPTS
        base_delay = 1
        max_delay = 60
        websocket_enabled = True
        
        logger.info(f"Запуск стабильного WebSocket соединения: {url}")
        
        while self.is_running:
            if not websocket_enabled and not self.config.polymarket.WEBSOCKET_FALLBACK_ENABLED:
                logger.error("WebSocket отключен и fallback запрещен, ожидание...")
                await asyncio.sleep(30)
                websocket_enabled = True
                continue
                
            if not websocket_enabled:
                # Fallback на HTTP polling если WebSocket не работает
                logger.warning("WebSocket отключен, используется HTTP polling как fallback")
                await self._http_polling_fallback()
                await asyncio.sleep(30)  # Проверяем каждые 30 секунд, можно ли восстановить WebSocket
                websocket_enabled = True  # Пробуем снова
                continue
                
            try:
                # Получаем список рынков для подписки на их asset_ids
                markets = self.get_markets()
                if not markets or len(markets) == 0:
                    logger.warning("Нет доступных рынков для WebSocket подписки, используется HTTP polling")
                    await self._http_polling_fallback()
                    await asyncio.sleep(60)
                    continue
                
                # Извлекаем asset_ids из первых 10 рынков (чтобы не перегружать)
                asset_ids = []
                logger.info(f"🔍 Извлечение asset_ids из {min(len(markets), 10)} рынков...")
                
                for i, market in enumerate(markets[:10]):
                    market_question = market.get('question', 'Неизвестный рынок')[:50]
                    logger.debug(f"📊 Рынок #{i+1}: {market_question}")
                    
                    # Сначала пробуем outcomes (старый формат)
                    outcomes = market.get('outcomes', [])
                    if outcomes:
                        logger.debug(f"   📋 Найдены outcomes: {len(outcomes)}")
                        for j, outcome in enumerate(outcomes):
                            asset_id = outcome.get('asset_id')
                            if asset_id:
                                asset_ids.append(asset_id)
                                logger.debug(f"   ✅ Asset ID #{j+1}: {asset_id[:20]}...")
                    
                    # Затем пробуем tokens (новый формат)
                    tokens = market.get('tokens', [])
                    if tokens:
                        logger.debug(f"   🎯 Найдены tokens: {len(tokens)}")
                        for j, token in enumerate(tokens):
                            if isinstance(token, dict):
                                # Ищем token_id как asset_id
                                token_id = token.get('token_id')
                                if token_id:
                                    asset_ids.append(token_id)
                                    logger.debug(f"   ✅ Token ID #{j+1}: {token_id[:20]}...")
                            elif isinstance(token, str):
                                # Если token - это просто строка
                                asset_ids.append(token)
                                logger.debug(f"   ✅ Token #{j+1}: {token[:20]}...")
                
                # Убираем дубликаты
                asset_ids = list(set(asset_ids))
                logger.info(f"🎯 Собрано уникальных asset_ids: {len(asset_ids)}")
                
                if not asset_ids:
                    logger.warning("❌ Не найдены asset_ids для подписки, используется HTTP polling")
                    await self._http_polling_fallback()
                    await asyncio.sleep(60)
                    continue
                
                logger.info(f"🚀 Подписка на {len(asset_ids)} asset_ids через WebSocket")
                
                # Современный подход с async for для автоматического переподключения
                async for websocket in websockets.connect(
                    url,
                    ping_interval=self.config.polymarket.WEBSOCKET_PING_INTERVAL,
                    ping_timeout=self.config.polymarket.WEBSOCKET_PING_TIMEOUT,
                    close_timeout=10,  # Таймаут закрытия 10 секунд
                    max_size=2**20,    # Максимальный размер сообщения 1MB
                    compression=None   # Отключаем компрессию для скорости
                ):
                    try:
                        self.websocket = websocket
                        self.is_connected = True
                        connection_attempts = 0  # Сбрасываем счетчик при успешном подключении
                        
                        logger.info("WebSocket подключен успешно, подписка на рынки...")
                        
                        # Правильная подписка согласно документации Polymarket
                        subscription_message = {
                            "assets_ids": asset_ids,
                            "type": "market"
                        }
                        await websocket.send(json.dumps(subscription_message))
                        logger.info(f"Отправлена подписка на {len(asset_ids)} assets")
                        
                        # Уведомляем о восстановлении WebSocket соединения только при повторном подключении
                        if connection_attempts > 0:
                            from src.telegram_bot import telegram_notifier
                            await telegram_notifier.send_message(
                                "🔌 <b>WebSocket восстановлен</b>\n\n"
                                f"✅ Подписка на {len(asset_ids)} рынков\n"
                                "⚡ Скорость реакции: <1 секунды\n\n"
                                "⏰ <i>{}</i>".format(datetime.now().strftime('%H:%M:%S'))
                            )
                        
                        # Создаем задачу для периодических PING сообщений
                        ping_task = asyncio.create_task(self._websocket_ping_task(websocket))
                        
                        # Основной цикл получения сообщений
                        async for message in websocket:
                            try:
                                data = json.loads(message)
                                logger.debug(f"📨 WebSocket сообщение: {type(data)} - {str(data)[:200]}")
                                
                                # Обрабатываем разные форматы сообщений
                                if isinstance(data, dict):
                                    # Если сообщение - словарь, фильтруем по типу события
                                    if data.get('event_type') in ['book', 'price_change', 'last_trade_price']:
                                        await self.message_handler(data)
                                elif isinstance(data, list):
                                    # Если сообщение - список, обрабатываем каждый элемент
                                    for item in data:
                                        if isinstance(item, dict) and item.get('event_type') in ['book', 'price_change', 'last_trade_price']:
                                            await self.message_handler(item)
                                else:
                                    logger.debug(f"🤷 Неизвестный формат WebSocket сообщения: {type(data)}")
                                    
                            except json.JSONDecodeError:
                                logger.warning(f"❌ Не удалось декодировать WebSocket сообщение: {message[:100]}")
                            except Exception as e:
                                logger.error(f"❌ Ошибка обработки WebSocket сообщения: {e}")
                                logger.debug(f"🔍 Проблемное сообщение: {message[:500]}")
                        
                        # Отменяем ping задачу при выходе из цикла
                        ping_task.cancel()
                        
                    except websockets.exceptions.ConnectionClosed as e:
                        self.is_connected = False
                        logger.warning(f"WebSocket соединение закрыто: {e}")
                        # async for автоматически попытается переподключиться
                        continue
                        
                    except Exception as e:
                        self.is_connected = False
                        logger.error(f"Ошибка в WebSocket цикле: {e}")
                        break
                        
            except Exception as e:
                self.is_connected = False
                connection_attempts += 1
                
                if connection_attempts >= max_attempts:
                    logger.error(f"Превышено максимальное количество попыток подключения WebSocket ({max_attempts})")
                    
                    if self.config.polymarket.WEBSOCKET_FALLBACK_ENABLED:
                        websocket_enabled = False
                        # Уведомляем о переходе на HTTP polling
                        from src.telegram_bot import telegram_notifier
                        await telegram_notifier.send_message(
                            "⚠️ <b>WebSocket недоступен</b>\n\n"
                            "🔄 Переключение на HTTP polling\n"
                            "📊 Задержка: до 60 секунд\n"
                            "🔧 Попытка восстановления каждые 30 сек\n\n"
                            "⏰ <i>{}</i>".format(datetime.now().strftime('%H:%M:%S'))
                        )
                        continue
                    else:
                        logger.error("Fallback отключен, WebSocket будет пытаться переподключиться...")
                        connection_attempts = 0  # Сбрасываем для бесконечных попыток
                
                # Exponential backoff с jitter
                delay = min(base_delay * (2 ** min(connection_attempts, 6)) + random.uniform(0, 1), max_delay)
                logger.warning(f"WebSocket подключение не удалось (попытка {connection_attempts}/{max_attempts}), "
                             f"повтор через {delay:.1f} сек: {e}")
                await asyncio.sleep(delay)

    async def _http_polling_fallback(self):
        """HTTP polling как fallback когда WebSocket не работает."""
        try:
            # Имитируем получение рынков через HTTP API
            # В реальности здесь был бы запрос к API для получения новых рынков
            logger.debug("HTTP polling: проверка новых рынков...")
            
            # Можно добавить логику для периодической проверки API
            # markets = self.get_markets()
            # for market in markets:
            #     await self.message_handler({"type": "market", "data": market})
            
        except Exception as e:
            logger.error(f"Ошибка HTTP polling fallback: {e}")

    async def _websocket_ping_task(self, websocket):
        """Задача для отправки периодических PING сообщений"""
        try:
            while self.is_running and not websocket.closed:
                await asyncio.sleep(10)  # PING каждые 10 секунд согласно документации
                if not websocket.closed:
                    await websocket.send("PING")
                    logger.debug("Отправлен WebSocket PING")
        except Exception as e:
            logger.warning(f"Ошибка в PING задаче: {e}")

    def stop_websocket(self):
        """Останавливает WebSocket соединение."""
        logger.info("Остановка WebSocket соединения...")
        self.is_running = False
        
        if self.websocket and self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self.websocket.close(), self.loop)
            
        if self.ws_thread and self.ws_thread.is_alive():
            self.ws_thread.join(timeout=5)


class PolymarketClientException(Exception):
    pass
