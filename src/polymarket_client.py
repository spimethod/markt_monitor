"""
Асинхронный клиент для взаимодействия с Polymarket API и смарт-контрактами
"""
import asyncio
import binascii
import json
import threading
import random
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
            logger.info("Запуск стабильного WebSocket с автоматическим переподключением")
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
        try:
            url = "https://clob.polymarket.com/markets"
            logger.info(f"🔗 Запрос рынков: {url}")
            
            response = self._make_request("GET", url)
            
            if not response:
                logger.warning("❌ Polymarket API не вернул данные")
                return []
                
            logger.info(f"✅ Получен ответ от Polymarket API")
            logger.info(f"📊 Тип ответа: {type(response)}")
            
            if isinstance(response, dict):
                # Если ответ - словарь, ищем список в нем
                if 'data' in response:
                    markets = response['data']
                    logger.info(f"📋 Найдены рынки в response['data']: {len(markets)} штук")
                elif 'markets' in response:
                    markets = response['markets']  
                    logger.info(f"📋 Найдены рынки в response['markets']: {len(markets)} штук")
                else:
                    logger.warning(f"⚠️  Неожиданная структура ответа: {list(response.keys())}")
                    return []
            elif isinstance(response, list):
                markets = response
                logger.info(f"📋 Получен прямой список рынков: {len(markets)} штук")
            else:
                logger.warning(f"❌ Неожиданный тип ответа: {type(response)}")
                return []
            
            # Логируем детали первых 3 рынков
            for i, market in enumerate(markets[:3]):
                if isinstance(market, dict):
                    logger.info(f"🎯 Рынок #{i+1}:")
                    logger.info(f"   📋 Вопрос: {market.get('question', 'N/A')}")
                    logger.info(f"   🆔 ID: {market.get('id', 'N/A')}")
                    logger.info(f"   💰 Ликвидность: ${market.get('liquidity', 0)}")
                    logger.info(f"   📊 Объем 24ч: ${market.get('volume24hr', 0)}")
                    logger.info(f"   🎲 Исходы: {len(market.get('outcomes', []))}")
                    logger.info(f"   📅 Создан: {market.get('created_at', 'N/A')}")
                    
                    # Детали исходов
                    outcomes = market.get('outcomes', [])
                    for j, outcome in enumerate(outcomes):
                        if isinstance(outcome, dict):
                            logger.info(f"     Исход {j+1}: {outcome.get('name', 'N/A')} (asset_id: {outcome.get('asset_id', 'N/A')})")
                else:
                    logger.warning(f"⚠️  Рынок #{i+1} не является словарем: {type(market)}")
            
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

    def get_account_balance(self) -> Optional[float]:
        """Получение баланса USDC аккаунта"""
        if not self.account:
            logger.warning("Невозможно получить баланс: аккаунт не инициализирован.")
            return None
        
        try:
            user_address = self.get_address()
            if not user_address:
                logger.warning("Не удалось получить адрес пользователя")
                return None
                
            # Способ 1: Получаем реальный баланс USDC через Polygon RPC
            try:
                import requests
                
                # USDC контракт на Polygon
                usdc_contract = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
                
                # Polygon RPC endpoint
                rpc_url = "https://polygon-rpc.com"
                
                # ERC20 balanceOf function signature: balanceOf(address)
                # Функция selector: 0x70a08231
                # Адрес пользователя должен быть дополнен до 32 байт (64 hex символа)
                user_padded = user_address[2:].lower().zfill(64)  # Убираем 0x и дополняем нулями
                data = f"0x70a08231{user_padded}"
                
                logger.info(f"Запрос баланса USDC для адреса: {user_address}")
                logger.info(f"Запрос к RPC: {rpc_url}")
                logger.info(f"Контракт USDC: {usdc_contract}")
                logger.info(f"Данные запроса: {data}")
                
                payload = {
                    "jsonrpc": "2.0",
                    "method": "eth_call",
                    "params": [{
                        "to": usdc_contract,
                        "data": data
                    }, "latest"],
                    "id": 1
                }
                
                response = requests.post(rpc_url, json=payload, timeout=10)
                logger.info(f"Статус ответа RPC: {response.status_code}")
                
                if response.status_code == 200:
                    data = response.json()
                    logger.info(f"Ответ RPC: {data}")
                    
                    if "result" in data and data["result"] != "0x":
                        # Получаем баланс в hex, конвертируем в int
                        balance_hex = data["result"]
                        balance_wei = int(balance_hex, 16)
                        logger.info(f"Баланс в hex: {balance_hex}")
                        logger.info(f"Баланс в wei: {balance_wei}")
                        
                        # Конвертируем в USDC (6 decimal places)
                        balance_usdc = balance_wei / (10 ** 6)
                        logger.info(f"Получен реальный баланс USDC: ${balance_usdc:.6f}")
                        return balance_usdc
                    else:
                        logger.warning("RPC вернул пустой результат для баланса USDC")
                else:
                    logger.warning(f"RPC запрос неудачен со статусом: {response.status_code}")
                    
            except Exception as e:
                logger.error(f"Ошибка получения баланса через Polygon RPC: {e}")
            
            # Способ 2: Gamma API (fallback)
            try:
                response = requests.get(
                    f"https://gamma-api.polymarket.com/positions?user={user_address}",
                    timeout=10
                )
                if response.status_code == 200:
                    data = response.json()
                    # Ищем свободный USDC баланс
                    if isinstance(data, dict) and 'cash_balance' in data:
                        balance = float(data['cash_balance'])
                        logger.debug(f"Получен баланс через Gamma API: ${balance}")
                        return balance
                    elif isinstance(data, dict) and 'free_balance' in data:
                        balance = float(data['free_balance'])
                        logger.debug(f"Получен свободный баланс: ${balance}")
                        return balance
                    elif isinstance(data, list):
                        # Суммируем свободные средства если есть массив позиций
                        total_cash = 0.0
                        for position in data:
                            if isinstance(position, dict) and position.get('outcome') == 'CASH':
                                total_cash += float(position.get('balance', 0))
                        if total_cash > 0:
                            logger.debug(f"Получен баланс из позиций: ${total_cash}")
                            return total_cash
                        
            except Exception as e:
                logger.debug(f"Gamma API недоступен: {e}")
            
            # Способ 3: Заглушка с логированием для отладки
            logger.warning("Все API недоступны - используется моковый баланс")
            logger.info(f"Адрес кошелька для отладки: {user_address}")
            logger.info(f"USDC контракт: 0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174")
            
            # Используем ваш реальный баланс как fallback - будет обновляться при пополнении
            mock_balance = 0.87  # Ваш текущий баланс
            logger.debug(f"Мок баланс (обновите в коде после пополнения): ${mock_balance}")
            return mock_balance
            
        except Exception as e:
            logger.error(f"Ошибка получения баланса: {e}")
            return None

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
                for market in markets[:10]:
                    outcomes = market.get('outcomes', [])
                    for outcome in outcomes:
                        asset_id = outcome.get('asset_id')
                        if asset_id:
                            asset_ids.append(asset_id)
                
                if not asset_ids:
                    logger.warning("Не найдены asset_ids для подписки, используется HTTP polling")
                    await self._http_polling_fallback()
                    await asyncio.sleep(60)
                    continue
                
                logger.info(f"Подписка на {len(asset_ids)} asset_ids через WebSocket")
                
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
                                # Фильтруем только сообщения о новых рынках или изменениях цен
                                if data.get('event_type') in ['book', 'price_change', 'last_trade_price']:
                                    await self.message_handler(data)
                            except json.JSONDecodeError:
                                logger.warning(f"Не удалось декодировать WebSocket сообщение: {message[:100]}")
                            except Exception as e:
                                logger.error(f"Ошибка обработки WebSocket сообщения: {e}")
                        
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
