"""
Главный файл для запуска Polymarket Trading Bot
"""

import asyncio
import signal
import sys
from loguru import logger

from src.config.settings import config
from src.trading_engine import TradingEngine


class PolymarketTradingBot:
    """Главный класс торгового бота"""
    
    def __init__(self):
        self.trading_engine = None
        self.is_running = False
    
    async def start(self):
        """Запуск бота"""
        try:
            logger.info("=== Запуск Polymarket Trading Bot ===")
            logger.info(f"Конфигурация: {config.to_dict()}")
            
            # Создаем торговый движок
            self.trading_engine = TradingEngine()
            self.is_running = True
            
            # Настраиваем обработчики сигналов для graceful shutdown
            self._setup_signal_handlers()
            
            # Запускаем торговый движок
            await self.trading_engine.start()
            
        except KeyboardInterrupt:
            logger.info("Получен сигнал остановки (Ctrl+C)")
            await self.stop()
        except Exception as e:
            logger.error(f"Критическая ошибка: {e}")
            await self.stop()
            sys.exit(1)
    
    async def stop(self):
        """Остановка бота"""
        try:
            logger.info("Остановка Polymarket Trading Bot...")
            self.is_running = False
            
            if self.trading_engine:
                await self.trading_engine.stop()
            
            logger.info("=== Polymarket Trading Bot остановлен ===")
            
        except Exception as e:
            logger.error(f"Ошибка при остановке: {e}")
    
    def _setup_signal_handlers(self):
        """Настройка обработчиков сигналов"""
        def signal_handler(signum, frame):
            logger.info(f"Получен сигнал {signum}")
            self.is_running = False
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)


async def main():
    """Главная функция"""
    bot = PolymarketTradingBot()
    await bot.start()


if __name__ == "__main__":
    try:
        # Запускаем бота
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Программа прервана пользователем")
    except Exception as e:
        logger.error(f"Неожиданная ошибка: {e}")
        sys.exit(1) 