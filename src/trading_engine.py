"""
Основной торговый движок для Polymarket
Включает мониторинг новых рынков, фильтрацию и автоматическую торговлю
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, Optional, Set, Tuple
from loguru import logger

from src.config.settings import config
from src.polymarket_client import PolymarketClient
from src.telegram_bot import telegram_notifier


class MarketFilter:
    """Фильтр рынков!"""
    def __init__(self):
        self.strategy_params = config.get_strategy_params()
        self.processed_markets: Set[str] = set()
        
        # Инициализируем кэш для отслеживания новых рынков
        self.known_markets: Set[str] = set()
        self.new_markets_timestamps: Dict[str, datetime] = {}
        
        # Рынки с активными позициями - не исключаются по времени
        self.markets_with_positions: Set[str] = set()
        
        logger.info("Инициализирован фильтр рынков с кэшем для отслеживания новых рынков")

    def cleanup_old_markets(self):
        """Очищает устаревшие рынки из кэша (кроме рынков с активными позициями)"""
        current_time = datetime.utcnow()
        expired_markets = []
        
        for market_id, discovery_time in self.new_markets_timestamps.items():
            # Не удаляем рынки с активными позициями
            if hasattr(self, 'markets_with_positions') and market_id in self.markets_with_positions:
                logger.debug(f"🔒 Рынок {market_id} сохранен в кэше (есть активная позиция)")
                continue
                
            time_diff = current_time - discovery_time
            if time_diff.total_seconds() > (config.trading.TIME_WINDOW_MINUTES * 60):
                expired_markets.append(market_id)
        
        for market_id in expired_markets:
            del self.new_markets_timestamps[market_id]
            
        if expired_markets:
            logger.debug(f"🧹 Очищены {len(expired_markets)} устаревших рынков из кэша")

    def is_binary_market(self, market_data: Dict) -> bool:
        """Проверяет, что рынок бинарный (2 исхода)"""
        # Проверяем tokens (новый формат)
        tokens = market_data.get("tokens", [])
        if tokens:
            token_count = len(tokens)
            logger.info(f"      🔍 Бинарность (tokens): {token_count} токенов")
            if token_count != 2:
                logger.info(f"      ❌ Не бинарный: {token_count} токенов (нужно 2)")
                return False
            logger.info(f"      ✅ Бинарный рынок: {token_count} токенов")
            return True
        
        # Fallback на outcomes (старый формат)
        outcomes = market_data.get("outcomes", [])
        outcome_count = len(outcomes)
        logger.info(f"      🔍 Бинарность (outcomes): {outcome_count} исходов")
        if outcome_count != 2:
            logger.info(f"      ❌ Не бинарный: {outcome_count} исходов (нужно 2)")
            return False
        logger.info(f"      ✅ Бинарный рынок: {outcome_count} исходов")
        return True

    def check_liquidity_requirement(self, market_data: Dict) -> bool:
        """Проверяет требования к ликвидности"""
        # Polymarket /markets API не возвращает liquidity
        # Вместо этого проверяем, что рынок активен и принимает ордера
        is_active = market_data.get("active", False)
        accepts_orders = market_data.get("accepting_orders", False)
        is_closed = market_data.get("closed", True)
        
        logger.info(f"      🔍 Ликвидность: active={is_active}, accepts_orders={accepts_orders}, closed={is_closed}")
        
        # Рынок должен быть активен, принимать ордера и не быть закрытым
        if is_active and accepts_orders and not is_closed:
            logger.info(f"      ✅ Рынок активен и принимает ордера")
            return True
        else:
            logger.info(f"      ❌ Рынок неактивен: active={is_active}, accepts_orders={accepts_orders}, closed={is_closed}")
            return False

    def check_time_window(self, market_data: Dict) -> Tuple[bool, str]:
        """Проверяет, что рынок недавно обнаружен или имеет активные позиции"""
        
        # Получаем ID рынка
        market_id = market_data.get("question_id") or market_data.get("condition_id") or market_data.get("market_slug")
        if not market_id:
            return False, "Отсутствует ID рынка для проверки времени"
        
        # Если рынок имеет активные позиции - всегда разрешаем торговлю
        if hasattr(self, 'markets_with_positions') and market_id in self.markets_with_positions:
            logger.info(f"      ✅ Рынок {market_id} имеет активную позицию - пропускаем проверку времени")
            return True, "Рынок с активной позицией"
        
        # Инициализируем кэш, если его нет
        if not hasattr(self, 'known_markets'):
            self.known_markets = set()
            logger.info("Инициализирован кэш рынков для отслеживания новых")
        
        # Если рынок уже известен - пропускаем
        if market_id in self.known_markets:
            logger.info(f"      ❌ Рынок был обнаружен ранее")
            return False, "Рынок был обнаружен ранее"
        
        # Новый рынок - добавляем в кэш
        self.known_markets.add(market_id)
        
        market_question = market_data.get('question', 'Неизвестный рынок')[:50]
        logger.info(f"      🆕 НОВЫЙ РЫНОК обнаружен: {market_question}...")
        logger.info(f"      🆔 ID: {market_id}")
        logger.info(f"      ⏰ Время обнаружения: {datetime.utcnow().strftime('%H:%M:%S')}")
        
        return True, "Новый рынок обнаружен"

    def should_trade_market(self, market_data: Dict) -> Tuple[bool, str]:
        # Получаем ID рынка из правильных полей
        market_id = market_data.get("question_id") or market_data.get("condition_id") or market_data.get("market_slug")
        if not market_id:
            return False, "Отсутствует ID рынка"

        if market_id in self.processed_markets:
            return False, "Рынок уже обработан"

        # Проверяем бинарность рынка
        if not self.is_binary_market(market_data):
            return False, "Не бинарный рынок"

        # Проверяем ликвидность
        if not self.check_liquidity_requirement(market_data):
            return False, "Рынок неактивен или не принимает ордера"

        # Проверяем временное окно
        time_check_result, time_reason = self.check_time_window(market_data)
        if not time_check_result:
            return False, time_reason

        self.processed_markets.add(market_id)
        return True, "Рынок подходит для торговли"


class TradingEngine:
    """Основной торговый движок"""
    def __init__(self):
        self.client = PolymarketClient()
        self.market_filter = MarketFilter()
        self.is_running = False
        self.stats = {"total_trades": 0, "successful_trades": 0, "total_profit": 0.0}

        # Торговля включена по умолчанию
        self.is_trading_enabled = True
        
        if self.client.get_address():
            logger.info(f"Торговый движок инициализирован для аккаунта: {self.client.get_address()}")
        else:
            logger.warning("PRIVATE_KEY не установлен. Торговля будет недоступна до установки ключа.")
            self.is_trading_enabled = False

    async def start(self):
        logger.info("Запуск торгового движка...")
        self.is_running = True
        telegram_notifier.set_trading_engine(self)

        tasks = [
            asyncio.create_task(self._market_monitor_task()),
        ]
        # Запускаем мониторинг позиций только если торговля включена
        if self.is_trading_enabled:
            tasks.append(asyncio.create_task(self._position_monitor_task()))

        # Запускаем бота после настройки задач
        await telegram_notifier.start_bot()

        await asyncio.gather(*tasks, return_exceptions=True)

    async def stop(self):
        logger.info("Остановка торгового движка...")
        self.is_running = False
        self.client.stop_websocket()
        await telegram_notifier.stop_bot()

    async def _market_monitor_task(self):
        logger.info("Запуск мониторинга рынков...")
        while self.is_running:
            try:
                logger.info("🔍 Поиск новых рынков...")
                
                # 1. Основной источник - Subgraph
                markets = await self.client.get_new_markets(max_age_minutes=10)
                
                # 2. Обработка ответа
                if markets is None:
                    # Ошибка в источнике, активируем fallback
                    logger.warning("🚨 Основной источник данных (Subgraph) не ответил. Активация Fallback...")
                    markets = self.client.get_all_markets_fallback(max_age_minutes=10)
                    
                    # Фильтруем уже обработанные в fallback
                    markets = [m for m in markets if m.get('id') not in self.market_filter.processed_markets]

                if not markets:
                    logger.info("📊 Новых рынков для анализа не найдено.")
                    await asyncio.sleep(60)
                    continue
                
                logger.info(f"📊 Получено {len(markets)} рынков для анализа")
                
                new_markets_found = 0
                suitable_markets = 0
                
                for i, market in enumerate(markets, 1):
                    # Получаем ID из правильных полей API
                    market_id = market.get("id") or market.get("conditionId")
                    market_question = market.get("question", "Неизвестный рынок")
                    
                    logger.info(f"🔍 АНАЛИЗ РЫНКА #{i}/{len(markets)}")
                    logger.info(f"   📋 Вопрос: {market_question}")
                    logger.info(f"   🆔 ID: {market_id}")
                    
                    # Детальная информация о рынке из Subgraph
                    created_timestamp = market.get('createdTimestamp')
                    if created_timestamp:
                        # Обрабатываем разные форматы timestamp
                        if isinstance(created_timestamp, str) and "Z" in created_timestamp:
                             created_dt = datetime.fromisoformat(created_timestamp.replace("Z", "+00:00"))
                             created_timestamp = int(created_dt.timestamp())
                        else:
                             created_dt = datetime.fromtimestamp(int(created_timestamp))
                        
                        age_seconds = int(time.time()) - int(created_timestamp)
                        age_str = f"{age_seconds // 60} мин {age_seconds % 60} сек"
                    else:
                        created_dt = "N/A"
                        age_str = "N/A"

                    logger.info(f"   📊 ДАННЫЕ РЫНКА:")
                    logger.info(f"      📅 Создан: {created_dt}")
                    logger.info(f"      ⏰ Возраст: {age_str}")
                    logger.info(f"      🎮 Активен: {market.get('active', False)}")
                    logger.info(f"      💱 Принимает ордера: {market.get('acceptingOrders', False)}")
                    
                    # Детальная информация о токенах
                    tokens = market.get('tokens', [])
                    if tokens:
                        logger.info(f"   🎯 ТОКЕНЫ ({len(tokens)}):")
                        for j, token in enumerate(tokens, 1):
                            token_name = token.get('name') or token.get('outcome')
                            token_price = token.get('price', 'N/A')
                            logger.info(f"      #{j} {token_name}: цена {token_price}")
                    
                    # Проверяем, подходит ли рынок для торговли
                    should_trade, reason = self.market_filter.should_trade_market(market)
                    
                    if should_trade:
                        suitable_markets += 1
                        logger.info(f"   ✅ ПОДХОДИТ: {reason}")
                        
                        if self.is_trading_enabled:
                            await self._attempt_trade(market)
                            new_markets_found += 1
                        else:
                            logger.info("   ⚠️ Торговля отключена, ордер не размещен.")
                    else:
                        logger.info(f"   ❌ НЕ ПОДХОДИТ: {reason}")

                    logger.info("   ==================================================")
                    
                if new_markets_found > 0:
                    await telegram_notifier.send_search_summary(
                        total_markets=len(markets),
                        suitable_markets=suitable_markets,
                        new_markets=new_markets_found
                    )
                
                await asyncio.sleep(60)
                
            except Exception as e:
                logger.error(f"❌ Ошибка в цикле мониторинга рынков: {e}", exc_info=True)
                await telegram_notifier.send_error_notification(f"Ошибка мониторинга: {e}")
                await asyncio.sleep(60)

    async def _attempt_trade(self, market_data: Dict):
        """Пытается совершить сделку по заданному рынку"""
        try:
            target_token_id = self._get_target_token_id(market_data)
            if not target_token_id:
                logger.warning("Не найден целевой токен для торговли")
                return

            # Находим цену из данных о токенах
            price = None
            for token in market_data.get('tokens', []):
                if token.get('id') == target_token_id:
                    price_value = token.get('price')
                    try:
                        price = float(price_value)
                    except (TypeError, ValueError):
                        price = None
                    break

            if price is None:
                price = self.client.get_current_price(target_token_id)  # fallback

            if price is None or price <= 0:
                logger.warning("Не удалось определить цену токена — пропускаем рынок")
                return

            # Для стратегии NO проверяем лимит цены
            if config.trading.POSITION_SIDE.upper() == "NO" and price > config.trading.MAX_NO_PRICE:
                logger.info(f"Пропускаем рынок: цена NO {price:.4f} превышает лимит {config.trading.MAX_NO_PRICE}")
                return

            # Размер позиции в токенах
            position_size_usd = config.trading.POSITION_SIZE_USD
            size_tokens = position_size_usd / price

            side = "BUY"  # Покупаем целевой токен (YES или NO)

            order_result = await self.client.place_order(
                token_id=target_token_id,
                side=side,
                size=size_tokens,
                price=price,
                market_data=market_data
            )

            if order_result:
                self.stats["total_trades"] += 1
                await telegram_notifier.send_trade_notification({
                    "order_id": order_result.get("order_id"),
                    "token_id": target_token_id,
                    "side": side,
                    "size": size_tokens,
                    "price": price
                })

        except Exception as e:
            logger.error(f"Ошибка при попытке торговли: {e}", exc_info=True)
            await telegram_notifier.send_error_notification(f"Ошибка торговли: {e}")

    def _get_target_token_id(self, market_data: Dict) -> Optional[str]:
        """Возвращает ID целевого токена (например, 'NO')"""
        target_side = config.trading.POSITION_SIDE.upper() # 'BUY' или 'SELL'
        target_outcome_name = "NO" if target_side == 'BUY' else 'YES'
        
        for token in market_data.get('tokens', []):
            token_outcome = token.get('outcome', '').upper()
            if token_outcome == target_outcome_name:
                return token.get('id')
                
        logger.warning(f"Не найден токен для исхода '{target_outcome_name}'")
        return None

    async def _position_monitor_task(self):
        logger.info("Запуск мониторинга позиций...")
        while self.is_running:
            try:
                # Проверяем и закрываем позиции
                await self.client.check_and_close_positions()
                
                # Очищаем рынки без активных позиций
                await self._cleanup_markets_without_positions()
                
                await asyncio.sleep(config.trading.POSITION_MONITOR_INTERVAL_SECONDS)
            except Exception as e:
                logger.error(f"Ошибка мониторинга позиций: {e}")
                await asyncio.sleep(60)

    async def _cleanup_markets_without_positions(self):
        """Удаляет рынки из списка активных если для них нет открытых позиций"""
        try:
            if not hasattr(self.market_filter, 'markets_with_positions'):
                return
                
            markets_to_remove = []
            open_positions = await self.client.db_manager.get_open_positions()
            user_address = self.client.get_address()
            
            if not user_address:
                return
                
            user_positions = [p for p in open_positions if p.get('user_address') == user_address]
            active_market_ids = set(p.get('market_id') for p in user_positions if p.get('market_id'))
            
            # Находим рынки в списке активных, но без открытых позиций
            for market_id in self.market_filter.markets_with_positions:
                if market_id not in active_market_ids:
                    markets_to_remove.append(market_id)
            
            # Удаляем такие рынки
            for market_id in markets_to_remove:
                self.market_filter.markets_with_positions.discard(market_id)
                logger.info(f"🧹 Рынок {market_id} удален из списка активных (нет открытых позиций)")
                
        except Exception as e:
            logger.error(f"Ошибка очистки рынков без позиций: {e}")



    async def get_stats(self) -> Dict:
        open_positions_count = 0
        user_address = self.client.get_address()
        if user_address:
            # get_open_positions возвращает все позиции, фильтруем по нашему пользователю
            all_open_positions = await self.client.db_manager.get_open_positions()
            user_open_positions = [p for p in all_open_positions if p.get('user_address') == user_address]
            open_positions_count = len(user_open_positions)

        return {**self.stats, "open_positions": open_positions_count}

    def enable_trading(self):
        if not self.client.get_address():
            logger.error("Невозможно включить торговлю: PRIVATE_KEY не установлен.")
            return
        self.is_trading_enabled = True

    def disable_trading(self):
        self.is_trading_enabled = False
