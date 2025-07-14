"""
Асинхронный клиент для взаимодействия с Polymarket API и смарт-контрактами
"""
import asyncio
import binascii
import json
import threading
from typing import Dict, Optional, Any

import requests
import websockets
from eth_account.signers.local import LocalAccount
from loguru import logger
from web3 import Account, Web3
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
        self.web3 = Web3(Web3.HTTPProvider(self.config.web3.RPC_URL))
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
            self._start_websocket_listener()

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
        url = "https://clob.polymarket.com/markets"
        response = self._make_request("GET", url)
        return response.json() if response else []

    def get_current_price(self, token_id: str) -> Optional[float]:
        """Получение текущей цены токена"""
        # Эта функция требует реальной реализации
        logger.warning("Функция get_current_price не реализована и возвращает моковое значение.")
        return 0.5

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
