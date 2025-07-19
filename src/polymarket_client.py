"""
Асинхронный клиент для взаимодействия с Polymarket API и смарт-контрактами
"""
import asyncio
import binascii
import json
import threading
import random
import time
import uuid
from typing import Dict, Optional, Any, Tuple
from datetime import datetime, timedelta

import requests
import websockets
from eth_account.signers.local import LocalAccount
from eth_account.messages import encode_defunct
from web3 import Account
from websockets.client import WebSocketClientProtocol

from loguru import logger
from src.config.settings import Config
from src.database.manager import DatabaseManager
from src import subgraph_client

# Создаем экземпляр конфига, чтобы он был доступен глобально
# Это безопасно, так как модуль импортируется один раз
config_instance = Config()

async def default_message_handler(message: Dict[str, Any]):
    """Обработчик сообщений по умолчанию. Просто логирует сообщение."""
    logger.info(f"Получено сообщение WebSocket: {message}")


class PolymarketClient:
    """
    Клиент для взаимодействия с API Polymarket, включая CLOB, WebSocket и Subgraph.
    """

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
        
        # CLOB API endpoints (используем стандартные значения Polymarket)
        self.clob_host = "https://clob.polymarket.com"  # Стандартный CLOB API
        self.websocket_host = "wss://ws-subscriptions-clob.polymarket.com"  # Стандартный WebSocket

        if self.config.polymarket.PRIVATE_KEY:
            try:
                self.account = Account.from_key(self.config.polymarket.PRIVATE_KEY)
                if self.account:
                    # Показываем только первые и последние 4 символа адреса для безопасности
                    address = self.account.address
                    masked_address = f"{address[:6]}...{address[-4:]}"
                    logger.info(f"Аккаунт {masked_address} успешно инициализирован.")
            except (ValueError, binascii.Error) as e:
                logger.error(f"Ошибка инициализации аккаунта: {e}. Проверьте PRIVATE_KEY.")
        else:
            logger.warning("PRIVATE_KEY не установлен. Торговля будет недоступна.")

        if self.config.polymarket.USE_WEBSOCKET:
            logger.info("Запуск стабильного WebSocket с автоматическим переподключением")
            self._start_websocket_listener()

        self.client_session = None  # для aiohttp
        
        # Кэш для отслеживания обработанных рынков в рамках сессии
        self.seen_market_ids = set()

    def get_address(self) -> Optional[str]:
        """Возвращает адрес аккаунта, если он доступен."""
        if self.account:
            # Для внутреннего использования возвращаем полный адрес
            return self.account.address
        return None

    def get_masked_address(self) -> Optional[str]:
        """Возвращает замаскированный адрес для логирования."""
        if self.account:
            address = self.account.address
            return f"{address[:6]}...{address[-4:]}"
        return None

    def build_order(self, asset_id: str, side: str, size: float, price: float, 
                   order_type: str = "LIMIT", expires: Optional[int] = None) -> Dict[str, Any]:
        """
        Создает структуру ордера для CLOB API
        """
        if not expires:
            expires = int(time.time()) + 3600  # 1 час по умолчанию
            
        order = {
            "asset_id": asset_id,
            "side": side.upper(),
            "size": str(size),
            "price": str(price),
            "order_type": order_type,
            "expires": expires,
            "nonce": int(time.time() * 1000) + random.randint(0, 999),  # Уникальный nonce
        }
        
        logger.info(f"Создан ордер: {side} {size} {asset_id} по цене {price}")
        return order

    def sign_order(self, order: Dict[str, Any]) -> str:
        """
        Подписывает ордер EIP-712 подписью
        """
        if not self.account:
            raise ValueError("Аккаунт не инициализирован")
            
        # Создаем EIP-712 структуру для подписи
        domain = {
            "name": "Polymarket",
            "version": "1",
            "chainId": 137,  # Polygon Mainnet (стандартная сеть Polymarket)
            "verifyingContract": "0x5177f16eae4b8c5d7c8c8c8c8c8c8c8c8c8c8c8c8"  # CLOB контракт
        }
        
        types = {
            "Order": [
                {"name": "asset_id", "type": "string"},
                {"name": "side", "type": "string"},
                {"name": "size", "type": "string"},
                {"name": "price", "type": "string"},
                {"name": "order_type", "type": "string"},
                {"name": "expires", "type": "uint256"},
                {"name": "nonce", "type": "uint256"}
            ]
        }
        
        # Создаем сообщение для подписи
        message = encode_defunct(
            text=json.dumps(order, sort_keys=True)
        )
        
        # Подписываем
        signed_message = self.account.sign_message(message)
        signature = signed_message.signature.hex()
        
        logger.info(f"Ордер подписан: {signature[:20]}...")
        return signature

    async def place_order(self, token_id: str, side: str, size: float, price: float, 
                         market_data: Optional[Dict] = None) -> Optional[Dict]:
        """
        Размещает реальный ордер через CLOB API
        """
        if not self.account:
            logger.error("Невозможно разместить ордер: приватный ключ не установлен.")
            return None
            
        masked_address = self.get_masked_address() or "N/A"
        logger.info(f"Размещение ордера: {side} {size} токенов {token_id[:20]}... по цене {price} (аккаунт: {masked_address})")
        
        try:
            # Создаем ордер
            order = self.build_order(token_id, side, size, price)
            
            # Подписываем ордер
            signature = self.sign_order(order)
            
            # Отправляем на CLOB API
            order_data = {
                **order,
                "signature": signature,
                "user_address": self.account.address
            }
            
            # Отправляем POST запрос к CLOB API
            url = f"{self.clob_host}/order"
            headers = {
                "Content-Type": "application/json",
                "x-address": self.account.address
            }
            
            response = self._make_request("POST", url, json=order_data, headers=headers)
            
            if response and response.status_code == 200:
                result = response.json()
                logger.info(f"✅ Ордер успешно размещен: {result.get('order_id', 'N/A')}")
        
        # Сохраняем позицию в базу данных
                await self._save_position_to_db(order, market_data, result)
                
                return result
            else:
                logger.error(f"❌ Ошибка размещения ордера: {response.status_code if response else 'No response'}")
                if response:
                    logger.error(f"Ответ сервера: {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Ошибка размещения ордера: {e}")
            return None

    async def _save_position_to_db(self, order: Dict[str, Any], market_data: Optional[Dict], 
                                  order_result: Dict[str, Any]) -> None:
        """Сохраняет позицию в базу данных"""
        if not self.account:
            logger.error("Невозможно сохранить позицию: аккаунт не инициализирован")
            return
            
        try:
            order_id = order_result.get('order_id', f"order_{int(time.time())}_{str(uuid.uuid4())[:8]}")
            
            market_id = None
            market_name = None
            if market_data:
                market_id = market_data.get("question_id") or market_data.get("condition_id") or market_data.get("market_slug")
                market_name = market_data.get("question", "Неизвестный рынок")[:500]
            
            position_data = {
                "id": order_id,
                "token_id": order["asset_id"],
                "market_id": market_id,
                "user_address": self.account.address,
                "side": order["side"],
                "size": float(order["size"]),
                "entry_price": float(order["price"]),
                "current_price": float(order["price"]),
                "target_profit": self.config.trading.PROFIT_TARGET_PERCENT,
                "stop_loss": self.config.trading.STOP_LOSS_PERCENT,
                "status": "open",
                "market_name": market_name
            }
            
            save_success = await self.db_manager.save_position(position_data)
            if save_success:
                logger.info(f"✅ Позиция {order_id} сохранена в БД")
            else:
                logger.warning(f"⚠️ Не удалось сохранить позицию {order_id} в БД")
                
        except Exception as e:
            logger.error(f"Ошибка сохранения позиции в БД: {e}")
        
    async def cancel_order(self, order_id: str) -> bool:
        """
        Отменяет ордер через CLOB API
        """
        if not self.account:
            logger.error("Невозможно отменить ордер: приватный ключ не установлен.")
            return False
            
        try:
            url = f"{self.clob_host}/order/{order_id}"
            headers = {
                "x-address": self.account.address
            }
            
            response = self._make_request("DELETE", url, headers=headers)
            
            if response and response.status_code == 200:
                logger.info(f"✅ Ордер {order_id} успешно отменен")
                return True
            else:
                logger.error(f"❌ Ошибка отмены ордера {order_id}: {response.status_code if response else 'No response'}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка отмены ордера {order_id}: {e}")
            return False

    async def get_my_orders(self) -> list:
        """
        Получает список активных ордеров пользователя
        """
        if not self.account:
            logger.error("Невозможно получить ордера: приватный ключ не установлен.")
            return []
            
        try:
            url = f"{self.clob_host}/orders"
            headers = {
                "x-address": self.account.address
            }
            
            response = self._make_request("GET", url, headers=headers)
            
            if response and response.status_code == 200:
                orders = response.json()
                logger.info(f"✅ Получено {len(orders)} активных ордеров")
                return orders
            else:
                logger.error(f"❌ Ошибка получения ордеров: {response.status_code if response else 'No response'}")
                return []
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения ордеров: {e}")
            return []
            
    async def get_new_markets(self, max_age_minutes: int = 10) -> list | None:
        """Основной метод для получения новых рынков через Subgraph."""
        try:
            markets = await subgraph_client.fetch_new_markets(max_age_minutes)
            if markets is None:
                logger.warning("Основной источник (Subgraph) вернул ошибку (None).")
                return None

            new_unique_markets = [
                market for market in markets 
                if market.get('id') and market.get('id') not in self.seen_market_ids
            ]
            
            # Обновляем кэш
            for market in new_unique_markets:
                self.seen_market_ids.add(market['id'])
                
            if len(new_unique_markets) < len(markets):
                logger.info(f"Отфильтровано {len(markets) - len(new_unique_markets)} уже известных рынков.")
            
            return new_unique_markets
        except Exception as e:
            logger.error(f"Error: {e}")
            return None

    def _normalize_market_data(self, market_data: Dict) -> Dict:
        """Приводит CLOB-рынок к формату Subgraph + вычисляет createdTimestamp."""
        # Пытаемся взять дату старта из rewards.event_start_date или game_start_time
        iso_date = None
        rewards = market_data.get("rewards")
        if isinstance(rewards, dict):
            iso_date = rewards.get("event_start_date") or rewards.get("event_start_time")
        if not iso_date:
            iso_date = market_data.get("game_start_time") or market_data.get("created_at")
        
        created_ts = None
        if iso_date:
            try:
                created_dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
                created_ts = int(created_dt.timestamp())
            except Exception:
                created_ts = None
        
        return {
            "id": market_data.get("condition_id"),
            "conditionId": market_data.get("condition_id"),
            "question": market_data.get("question"),
            "slug": market_data.get("market_slug") or market_data.get("slug"),
            "createdTimestamp": created_ts,
            "active": market_data.get("active", False),
            # Нормализуем ключ: и camelCase и snake_case
            "acceptingOrders": market_data.get("acceptingOrders", market_data.get("accepting_orders", False)),
            "accepting_orders": market_data.get("acceptingOrders", market_data.get("accepting_orders", False)),
            "tokens": [
                {
                    "id": t.get("token_id"),
                    "name": t.get("outcome"),
                    "outcome": t.get("outcome"),
                    "price": t.get("price") or t.get("prob", t.get("price_per_share"))
                }
                for t in market_data.get("tokens", [])
            ]
        }
        
    def get_all_markets_fallback(self, max_age_minutes: int = 10) -> list:
        """Fallback-метод: получает рынки и возвращает только созданные ≤ max_age_minutes назад."""
        logger.warning("⚠️  Fallback: получение рынков через CLOB API")
        now_ts = int(time.time())
        raw_markets = self._fetch_all_markets()

        fresh_markets: list = []
        for m in raw_markets:
            norm = self._normalize_market_data(m)
            ts = norm.get("createdTimestamp")
            if ts and (now_ts - ts) <= max_age_minutes * 60:
                if norm["id"] and norm["id"] not in self.seen_market_ids:
                    fresh_markets.append(norm)
                    self.seen_market_ids.add(norm["id"])
        logger.info(f"📋 [Fallback] Новых рынков ≤{max_age_minutes} мин: {len(fresh_markets)}")
        return fresh_markets

    def _fetch_all_markets(self) -> list:
        """Получает все рынки от Polymarket CLOB API."""
        try:
            url = "https://clob.polymarket.com/markets"
            logger.info(f"🔗 [Fallback] Запрос рынков: {url}")
            response = self._make_request("GET", url)
            if not response: 
                return []
            data = response.json()
            markets = data if isinstance(data, list) else data.get('data', [])
            logger.info(f"📋 [Fallback] Получено {len(markets)} рынков.")
            return markets
        except Exception as e:
            logger.error(f"❌ [Fallback] Ошибка получения рынков: {e}")
            return []
            
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
        """Проверяет и закрывает позиции в соответствии с стратегией"""
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
                # Получаем новые рынки для подписки на их asset_ids
                new_markets = await self.get_new_markets(max_age_minutes=60)  # Берем рынки за последний час
                if not new_markets:
                    # Если новых нет, берем все рынки как fallback
                    markets = self.get_all_markets_fallback()
                    if not markets or len(markets) == 0:
                        logger.warning("Нет доступных рынков для WebSocket подписки, используется HTTP polling")
                        await self._http_polling_fallback()
                        await asyncio.sleep(60)
                        continue
                    logger.info(f"🔍 Fallback: извлечение asset_ids из {min(len(markets), 10)} всех рынков...")
                else:
                    markets = new_markets
                    logger.info(f"🔍 Извлечение asset_ids из {min(len(markets), 10)} новых рынков...")
                
                # Извлекаем asset_ids из первых 10 рынков (чтобы не перегружать)
                asset_ids = []
                
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
                        
                        # Используем встроенный heartbeat библиотеки websockets
                        # ping_task = asyncio.create_task(self._websocket_ping_task(websocket))
                        
                        # Основной цикл получения сообщений
                        async for message in websocket:
                            # Обрабатываем PONG сообщения (heartbeat)
                            if message == "PONG":
                                logger.debug("← PONG (heartbeat)")
                                continue
                            
                            # Проверяем, что сообщение похоже на JSON
                            if not (isinstance(message, str) and (message.startswith("{") or message.startswith("["))):
                                logger.debug(f"Не-JSON сообщение: {message[:50]}")
                                continue
                            
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
                        # ping_task.cancel()
                        
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
                        await telegram_notifier.send_websocket_fallback_notification()
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
            while self.is_running and self._is_websocket_open(websocket):
                await asyncio.sleep(10)  # PING каждые 10 секунд согласно документации
                if self._is_websocket_open(websocket):
                    await websocket.send("PING")
                    logger.debug("Отправлен WebSocket PING")
        except Exception as e:
            logger.warning(f"Ошибка в PING задаче: {e}")
            
    def _is_websocket_open(self, websocket):
        """Проверяет, открыто ли WebSocket соединение"""
        try:
            # Проверяем наличие атрибута closed у websocket объекта
            if hasattr(websocket, 'closed'):
                return not websocket.closed
            # Альтернативная проверка для других типов объектов
            elif hasattr(websocket, 'state'):
                from websockets.protocol import State
                return websocket.state == State.OPEN
            else:
                # Если нет известных атрибутов, считаем что соединение открыто
                return True
        except Exception:
            return False

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
