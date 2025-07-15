"""
Асинхронный клиент для взаимодействия с Polymarket API и смарт-контрактами
"""
import asyncio
import binascii
import json
import threading
from typing import Dict, Optional, Any
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
            # Временно отключаем WebSocket в production для стабильности
            logger.info("WebSocket отключен для стабильности работы в production")
            # self._start_websocket_listener()

    def get_address(self) -> Optional[str]:
        """Возвращает адрес аккаунта, если он доступен."""
        return self.account.address if self.account else None

    def place_order(self, token_id: str, side: str, size: float, price: float) -> Optional[Dict]:
        """
        Размещает ордер на покупку или продажу.
        """
        if not self.account:
            logger.error("Невозможно разместить ордер: приватный ключ не установлен.")
            return None
            
        logger.info(f"Размещение ордера: {side} {size} токенов {token_id} по цене {price}")
        # Здесь будет логика для реального размещения ордера
        order_data = {
            "token_id": token_id, "price": str(price), "size": str(size),
            "side": side, "status": "placed", "id": "mock_order_id"
        }
        return order_data

    def get_markets(self) -> list:
        """Получает список активных рынков"""
        try:
            url = "https://clob.polymarket.com/markets"
            response = self._make_request("GET", url)
            
            if not response:
                logger.warning("Не удалось получить ответ от API рынков")
                return []
            
            data = response.json()
            
            # Проверяем, что получили именно список
            if isinstance(data, list):
                logger.debug(f"Получено {len(data)} рынков из API")
                return data
            elif isinstance(data, dict):
                # Если API вернул объект с рынками внутри
                if 'data' in data and isinstance(data['data'], list):
                    logger.debug(f"Получено {len(data['data'])} рынков из API (в поле data)")
                    return data['data']
                elif 'markets' in data and isinstance(data['markets'], list):
                    logger.debug(f"Получено {len(data['markets'])} рынков из API (в поле markets)")
                    return data['markets']
                else:
                    logger.warning(f"API вернул объект без массива рынков: {list(data.keys())}")
                    return []
            else:
                logger.warning(f"API вернул неожиданный тип данных: {type(data)} - {str(data)[:100]}")
                return []
                
        except Exception as e:
            logger.error(f"Ошибка получения рынков: {e}")
            return []

    def get_current_price(self, token_id: str) -> Optional[float]:
        """Получение текущей цены токена"""
        # Эта функция требует реальной реализации
        logger.warning("Функция get_current_price не реализована и возвращает моковое значение.")
        return 0.5

    def get_account_balance(self) -> Optional[float]:
        """Получение баланса USDC аккаунта"""
        if not self.account:
            logger.warning("Невозможно получить баланс: аккаунт не инициализирован.")
            return None
        
        # Заглушка для баланса - в реальности здесь будет API запрос
        # В продакшн версии здесь должен быть запрос к Polymarket API
        mock_balance = 100.0  # $100 для тестирования
        logger.debug(f"Получен баланс аккаунта: ${mock_balance}")
        return mock_balance

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

            for trade in user_positions:
                current_price = self.get_current_price(trade['token_id'])
                if not current_price:
                    continue
                await self.db_manager.update_position_price(trade['id'], current_price)
                # ... остальная логика ...
        except Exception as e:
            logger.error(f"Ошибка при проверке и закрытии позиций: {e}")

    def stop_websocket(self):
        """Останавливает WebSocket соединение."""
        self.is_running = False
        if self.websocket and self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self.websocket.close(), self.loop)
        if self.ws_thread and self.ws_thread.is_alive():
            self.ws_thread.join(timeout=5)

    def _start_websocket_listener(self):
        """Запускает WebSocket слушатель в отдельном потоке."""
        self.ws_thread = threading.Thread(target=self._websocket_loop, daemon=True)
        self.ws_thread.start()

    def _websocket_loop(self):
        """Основной цикл для WebSocket соединения."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._websocket_handler())
        self.loop.close()

    async def _websocket_handler(self):
        """Обработчик WebSocket сообщений."""
        url = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
        while self.is_running:
            try:
                async with websockets.connect(url) as websocket:
                    self.websocket = websocket
                    self.is_connected = True
                    logger.info("WebSocket подключен, подписка на рынки...")
                    await websocket.send(json.dumps({"type": "market"}))
                    async for message in websocket:
                        try:
                            await self.message_handler(json.loads(message))
                        except json.JSONDecodeError:
                            logger.warning(f"Не удалось декодировать сообщение: {message}")
            except Exception as e:
                self.is_connected = False
                logger.error(f"Ошибка WebSocket: {e}. Переподключение через 5 секунд...")
                await asyncio.sleep(5)


class PolymarketClientException(Exception):
    pass
