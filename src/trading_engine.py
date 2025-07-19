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
                # Очищаем устаревшие рынки из кэша
                self.market_filter.cleanup_old_markets()
                
                logger.info("🔍 Поиск новых рынков...")
                # Получаем только новые рынки (не старше 10 минут)
                markets = self.client.get_new_markets(max_age_minutes=10)
                
                # Проверяем, что получили список
                if not isinstance(markets, list):
                    logger.warning(f"get_new_markets() вернул не список: {type(markets)}")
                    await asyncio.sleep(60)
                    continue
                
                if not markets:
                    logger.info("📊 Новых рынков не найдено (все старше 10 минут)")
                    await asyncio.sleep(60)
                    continue
                
                logger.info(f"📊 Получено {len(markets)} новых рынков для анализа")
                
                new_markets_found = 0
                suitable_markets = 0
                
                for i, market in enumerate(markets, 1):
                    # Получаем ID из правильных полей API
                    market_id = market.get("question_id") or market.get("condition_id") or market.get("market_slug")
                    market_question = market.get("question", "Неизвестный рынок")
                    
                    logger.info(f"🔍 АНАЛИЗ РЫНКА #{i}/{len(markets)}")
                    logger.info(f"   📋 Вопрос: {market_question}")
                    logger.info(f"   🆔 ID: {market_id}")
                    
                    # Детальная информация о рынке
                    logger.info(f"   📊 ДАННЫЕ РЫНКА:")
                    logger.info(f"      🎮 Активен: {market.get('active', False)}")
                    logger.info(f"      💱 Принимает ордера: {market.get('accepting_orders', False)}")
                    logger.info(f"      🔒 Закрыт: {market.get('closed', False)}")
                    logger.info(f"      📅 Создан: {market.get('created_at', 'N/A')}")
                    logger.info(f"      ⏰ Окончание: {market.get('end_date_iso', 'N/A')}")
                    logger.info(f"      💰 Минимальная ликвидность: {market.get('min_liquidity', 'N/A')}")
                    logger.info(f"      🏷️  Категория: {market.get('category', 'N/A')}")
                    
                    # Детальная информация о токенах
                    tokens = market.get('tokens', [])
                    if tokens:
                        logger.info(f"   🎯 ТОКЕНЫ ({len(tokens)}):")
                        for j, token in enumerate(tokens, 1):
                            if isinstance(token, dict):
                                logger.info(f"      #{j} ID: {token.get('id', 'N/A')}")
                                logger.info(f"         Название: {token.get('name', 'N/A')}")
                                logger.info(f"         Исход: {token.get('outcome', 'N/A')}")
                                logger.info(f"         Цена: {token.get('price', 'N/A')}")
                                logger.info(f"         Объем: {token.get('volume', 'N/A')}")
                                logger.info(f"         Ликвидность: {token.get('liquidity', 'N/A')}")
                    else:
                        logger.info(f"   ❌ Токены не найдены")
                    
                    # Анализ пригодности
                    should_trade, reason = self.market_filter.should_trade_market(market)
                    
                    if should_trade:
                        suitable_markets += 1
                        logger.info(f"   ✅ ПОДХОДЯЩИЙ РЫНОК!")
                        logger.info(f"   🎯 Причина: {reason}")
                        
                        if not self.is_trading_enabled:
                            logger.warning(f"   ⚠️  Торговля отключена (нет приватного ключа)")
                            await telegram_notifier.send_new_market_notification(market)
                            continue
                            
                        logger.info(f"   🚀 Попытка торговли...")
                        await self._attempt_trade(market)
                        
                        new_markets_found += 1
                    else:
                        logger.info(f"   ❌ НЕ ПОДХОДИТ: {reason}")
                    
                    logger.info(f"   {'='*50}")
                
                # Сводка по циклу
                if new_markets_found > 0:
                    logger.info(f"🎯 ИТОГ ПОИСКА: найдено {suitable_markets} подходящих рынков из {len(markets)}")
                    await telegram_notifier.send_search_summary(len(markets), suitable_markets, new_markets_found)
                else:
                    logger.info(f"🔍 Поиск завершен: проанализировано {len(markets)} рынков, новых подходящих не найдено")
                
                await asyncio.sleep(60)  # Проверяем каждую минуту
                
            except Exception as e:
                logger.error(f"Ошибка в мониторинге рынков: {e}")
                await asyncio.sleep(60)

    async def _attempt_trade(self, market_data: Dict):
        if not self.is_trading_enabled: return

        token_id = self._get_target_token_id(market_data)
        if not token_id: return

        price = self.client.get_current_price(token_id)
        if not price: return

        # Проверяем максимальную цену для позиции NO
        if config.trading.POSITION_SIDE == "NO" and price > config.trading.MAX_NO_PRICE:
            logger.info(f"Пропускаем рынок: цена NO {price:.4f} превышает максимум {config.trading.MAX_NO_PRICE}")
            return

        # Используем фиксированный размер позиции
        position_size_usd = config.trading.POSITION_SIZE_USD

        side = "BUY"
        size = position_size_usd / price

        order_result = await self.client.place_order(token_id, side, size, price, market_data)
        if order_result:
            self.stats["total_trades"] += 1
            logger.info(f"Сделка совершена: {order_result}")
            
            # Добавляем рынок в список с активными позициями 
            # чтобы он не исключался через 10 минут
            market_id = market_data.get("question_id") or market_data.get("condition_id") or market_data.get("market_slug")
            if market_id:
                self.market_filter.markets_with_positions.add(market_id)
                logger.info(f"📌 Рынок {market_id} добавлен в список с активными позициями")
        else:
            logger.warning(f"❌ Не удалось открыть позицию для рынка: {market_data.get('question', 'N/A')}")

    def _get_target_token_id(self, market_data: Dict) -> Optional[str]:
        for token in market_data.get("tokens", []):
            if config.trading.POSITION_SIDE == "YES" and "YES" in token.get("name", ""):
                return token.get("id")
            if config.trading.POSITION_SIDE == "NO" and "NO" in token.get("name", ""):
                return token.get("id")
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
