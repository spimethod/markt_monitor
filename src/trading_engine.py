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
    """Фильтр рынков по заданным критериям"""
    def __init__(self):
        self.strategy_params = config.get_strategy_params()
        self.processed_markets: Set[str] = set()

    def is_binary_market(self, market_data: Dict) -> bool:
        return len(market_data.get("outcomes", [])) == 2

    def check_liquidity_requirement(self, market_data: Dict) -> bool:
        return float(market_data.get("liquidity", 0)) >= config.trading.MIN_LIQUIDITY_USD

    def check_time_window(self, market_data: Dict) -> Tuple[bool, str]:
        """Проверяет, что рынок создан не позднее TIME_WINDOW_MINUTES назад"""
        created_at = market_data.get("created_at")
        if not created_at:
            # Если время создания неизвестно, пропускаем проверку
            logger.debug("Время создания рынка неизвестно, пропускаем проверку временного окна")
            return True, "Время создания неизвестно"
        
        try:
            # Парсим время создания (поддерживаем разные форматы)
            if isinstance(created_at, str):
                # Попробуем разные форматы даты
                for date_format in ["%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"]:
                    try:
                        market_created_time = datetime.strptime(created_at, date_format)
                        break
                    except ValueError:
                        continue
                else:
                    # Если ни один формат не подошел, используем текущее время
                    logger.warning(f"Не удалось распарсить время создания рынка: {created_at}")
                    return True, "Неподдерживаемый формат времени"
            elif isinstance(created_at, (int, float)):
                # Unix timestamp
                market_created_time = datetime.fromtimestamp(created_at)
            else:
                logger.warning(f"Неподдерживаемый тип времени создания: {type(created_at)}")
                return True, "Неподдерживаемый тип времени"
            
            # Проверяем временное окно
            time_diff = datetime.utcnow() - market_created_time
            time_window_delta = timedelta(minutes=config.trading.TIME_WINDOW_MINUTES)
            
            if time_diff <= time_window_delta:
                logger.debug(f"Рынок создан {time_diff.total_seconds():.0f} сек назад, в пределах окна {config.trading.TIME_WINDOW_MINUTES} мин")
                return True, f"Рынок в временном окне ({time_diff.total_seconds():.0f}s)"
            else:
                logger.debug(f"Рынок создан {time_diff.total_seconds():.0f} сек назад, вне окна {config.trading.TIME_WINDOW_MINUTES} мин")
                return False, f"Рынок слишком старый ({time_diff.total_seconds():.0f}s > {time_window_delta.total_seconds():.0f}s)"
                
        except Exception as e:
            logger.warning(f"Ошибка при проверке временного окна: {e}")
            return True, "Ошибка проверки времени"

    def should_trade_market(self, market_data: Dict) -> Tuple[bool, str]:
        market_id = market_data.get("id")
        if not market_id:
            return False, "Отсутствует ID рынка"

        if market_id in self.processed_markets:
            return False, "Рынок уже обработан"

        if not self.is_binary_market(market_data):
            return False, "Не бинарный рынок"

        if not self.check_liquidity_requirement(market_data):
            return False, "Недостаточная ликвидность"

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

        if self.client.get_address():
            logger.info(f"Торговый движок инициализирован для аккаунта: {self.client.get_address()}")
            self.is_trading_enabled = True
        else:
            logger.warning("PRIVATE_KEY не установлен. Торговля и управление позициями будут отключены.")
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
            # Добавляем задачи мониторинга баланса
            tasks.append(asyncio.create_task(self._balance_monitor_task()))
            tasks.append(asyncio.create_task(self._balance_check_task()))

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
                markets = self.client.get_markets()
                
                # Проверяем, что получили список
                if not isinstance(markets, list):
                    logger.warning(f"get_markets() вернул не список: {type(markets)}")
                    await asyncio.sleep(60)
                    continue
                
                logger.info(f"📊 Получено {len(markets)} рынков для анализа")
                
                new_markets_found = 0
                suitable_markets = 0
                
                for market in markets:
                    market_id = market.get("id")
                    market_question = market.get("question", "Неизвестный рынок")
                    
                    logger.debug(f"🎯 Анализ рынка: {market_question[:100]}...")
                    
                    should_trade, reason = self.market_filter.should_trade_market(market)
                    
                    if should_trade:
                        suitable_markets += 1
                        logger.info(f"✅ ПОДХОДЯЩИЙ РЫНОК найден!")
                        logger.info(f"   📋 Вопрос: {market_question}")
                        logger.info(f"   🆔 ID: {market_id}")
                        logger.info(f"   💰 Ликвидность: ${market.get('liquidity', 0):.2f}")
                        logger.info(f"   📊 Объем 24ч: ${market.get('volume24hr', 0):.2f}")
                        logger.info(f"   ✅ Причина: {reason}")
                        
                        # Проверяем баланс перед торговлей
                        current_balance = self.client.get_account_balance()
                        logger.info(f"   💳 Текущий баланс: ${current_balance:.6f}")
                        
                        if not self.is_trading_enabled:
                            logger.warning(f"   ⚠️  Торговля отключена (нет приватного ключа)")
                            await telegram_notifier.send_new_market_notification(market)
                            continue
                            
                        if current_balance and current_balance >= 0.01:  # Минимум 1 цент
                            logger.info(f"   🚀 Попытка торговли...")
                            await self._attempt_trade(market)
                        else:
                            logger.warning(f"   💸 Недостаточно средств для торговли (баланс: ${current_balance:.6f})")
                            await telegram_notifier.send_message(
                                f"💡 <b>Найден подходящий рынок</b>\n\n"
                                f"📋 {market_question[:200]}\n"
                                f"💰 Ликвидность: ${market.get('liquidity', 0):.2f}\n\n"
                                f"⚠️ <b>Торговля пропущена</b>\n"
                                f"💸 Недостаточно средств (${current_balance:.6f})"
                            )
                        
                        new_markets_found += 1
                    else:
                        logger.debug(f"   ❌ Пропущен: {reason}")
                
                # Сводка по циклу
                if new_markets_found > 0:
                    logger.info(f"🎯 ИТОГ ПОИСКА: найдено {suitable_markets} подходящих рынков из {len(markets)}")
                    await telegram_notifier.send_message(
                        f"🔍 <b>Поиск завершен</b>\n\n"
                        f"📊 Проанализировано: {len(markets)} рынков\n"
                        f"✅ Подходящих: {suitable_markets}\n"
                        f"🆕 Новых: {new_markets_found}"
                    )
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

        # Рассчитываем размер позиции с учетом лимита от баланса
        balance = self.client.get_account_balance()
        if not balance:
            logger.warning("Не удалось получить баланс аккаунта, пропускаем сделку")
            return
            
        max_position_from_balance = balance * (config.trading.MAX_POSITION_PERCENT_OF_BALANCE / 100)
        position_size_usd = min(config.trading.POSITION_SIZE_USD, max_position_from_balance)
        
        if position_size_usd < config.trading.POSITION_SIZE_USD:
            logger.info(f"Размер позиции ограничен балансом: ${position_size_usd:.2f} вместо ${config.trading.POSITION_SIZE_USD}")

        side = "BUY"
        size = position_size_usd / price

        order_result = self.client.place_order(token_id, side, size, price)
        if order_result:
            self.stats["total_trades"] += 1
            logger.info(f"Сделка совершена: {order_result}")

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
                # Эта логика теперь в PolymarketClient
                await self.client.check_and_close_positions()
                await asyncio.sleep(config.trading.POSITION_MONITOR_INTERVAL_SECONDS)
            except Exception as e:
                logger.error(f"Ошибка мониторинга позиций: {e}")
                await asyncio.sleep(60)

    async def _balance_monitor_task(self):
        logger.info("Запуск мониторинга баланса...")
        while self.is_running:
            try:
                await self.client.monitor_balance()
                await asyncio.sleep(config.trading.BALANCE_MONITOR_INTERVAL_SECONDS)
            except Exception as e:
                logger.error(f"Ошибка мониторинга баланса: {e}")
                await asyncio.sleep(60)

    async def _balance_check_task(self):
        logger.info("Запуск проверки баланса...")
        while self.is_running:
            try:
                await self.client.check_balance(config.trading.BALANCE_CHECK_FREQUENCY_SECONDS)
                await asyncio.sleep(config.trading.BALANCE_CHECK_FREQUENCY_SECONDS)
            except Exception as e:
                logger.error(f"Ошибка проверки баланса: {e}")
                await asyncio.sleep(60)

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
