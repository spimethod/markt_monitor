"""
Главный файл для запуска Polymarket Factory Monitor
Мониторит все фабрики Polymarket на Polygon
"""

import time
import signal
import sys
from typing import List, Dict, Any, cast
from web3 import Web3
from web3.providers import LegacyWebSocketProvider
from web3.types import FilterParams
from eth_utils import to_checksum_address, event_abi_to_log_topic
from loguru import logger

# ---------------------------------------------------------------------------
# WebSocket RPC (Alchemy)
# ---------------------------------------------------------------------------
POLYGON_WS = "wss://polygon-mainnet.g.alchemy.com/v2/fqlDOKopXL8QsZnEdCrkV"

# ---------------------------------------------------------------------------
# Актуальные фабрики Polymarket (июль 2025)
# ---------------------------------------------------------------------------
FACTORIES_RAW: List[str] = [
    "0x8B9805A2f595B6705e74F7310829f2d299D21522",  # FP-MM v1
    "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E",  # CLOB factory
    "0x7bB0f881F37331d77b58dcDFdB9a46f0BfA4eF4F",  # FP-MM v2
    "0xa9425A42E0B664F8B4F4B5f4b8224F7C7F3B3CdF",  # Parlay factory
]
FACTORIES = [to_checksum_address(a) for a in FACTORIES_RAW]

# ---------------------------------------------------------------------------
# Мини-ABI и topic0 для нужных событий
# ---------------------------------------------------------------------------
ABI_AMM: Dict[str, Any] = {
    "name": "MarketCreated", "type": "event", "anonymous": False,
    "inputs": [{"indexed": True, "name": "market", "type": "address"}]
}
ABI_CLOB: Dict[str, Any] = {
    "name": "OrderbookCreated", "type": "event", "anonymous": False,
    "inputs": [{"indexed": True, "name": "orderbook", "type": "address"},
               {"indexed": True, "name": "creator", "type": "address"}]
}
ABI_PARLAY: Dict[str, Any] = {
    "name": "ParlayCreated", "type": "event", "anonymous": False,
    "inputs": [{"indexed": True, "name": "parlay", "type": "address"},
               {"indexed": True, "name": "creator", "type": "address"}]
}

TOPIC_AMM = event_abi_to_log_topic(cast(Any, ABI_AMM))
TOPIC_CLOB = event_abi_to_log_topic(cast(Any, ABI_CLOB))
TOPIC_PARLAY = event_abi_to_log_topic(cast(Any, ABI_PARLAY))


class PolymarketFactoryMonitor:
    """Монитор фабрик Polymarket"""
    
    def __init__(self):
        self.w3 = None
        self.log_filter = None
        self.is_running = False
    
    def setup_connection(self):
        """Настройка подключения к Polygon"""
        try:
            logger.info("Подключение к Polygon WebSocket...")
            self.w3 = Web3(LegacyWebSocketProvider(POLYGON_WS))
            
            if not self.w3.is_connected():
                raise Exception("Не удалось подключиться к Polygon WS RPC")
            
            logger.info("✅ Подключение к Polygon установлено")
            
            # Создаем фильтр для всех фабрик
            self.log_filter = self.w3.eth.filter(cast(FilterParams, {
                "address": FACTORIES,
                "fromBlock": "latest",
                "topics": [[TOPIC_AMM.hex(), TOPIC_CLOB.hex(), TOPIC_PARLAY.hex()]]
            }))
            
            logger.info("✅ Фильтр событий создан")
            logger.info(f"📡 Мониторинг фабрик: {len(FACTORIES)} адресов")
            
        except Exception as e:
            logger.error(f"❌ Ошибка подключения: {e}")
            raise
    
    def process_event(self, log):
        """Обработка события создания рынка"""
        try:
            topic0 = log["topics"][0]
            
            if topic0 == TOPIC_AMM.hex():
                market = to_checksum_address("0x" + log["topics"][1].hex()[-40:])
                logger.info(f"🆕 AMM market    {market}")
                
            elif topic0 == TOPIC_CLOB.hex():
                orderbook = to_checksum_address("0x" + log["topics"][1].hex()[-40:])
                creator = to_checksum_address("0x" + log["topics"][2].hex()[-40:])
                logger.info(f"🆕 CLOB orderbook {orderbook} | creator {creator}")
                
            elif topic0 == TOPIC_PARLAY.hex():
                parlay = to_checksum_address("0x" + log["topics"][1].hex()[-40:])
                creator = to_checksum_address("0x" + log["topics"][2].hex()[-40:])
                logger.info(f"🆕 Parlay        {parlay}  | creator {creator}")
                
        except Exception as e:
            logger.error(f"❌ Ошибка обработки события: {e}")
    
    def monitor_events(self):
        """Основной цикл мониторинга"""
        logger.info("🟢 Начинаю мониторинг новых рынков...")
        
        try:
            while self.is_running:
                # Получаем новые события
                for log in self.log_filter.get_new_entries():
                    self.process_event(log)
                
                # Пауза между проверками
                time.sleep(2)
                
        except KeyboardInterrupt:
            logger.info("⏹️ Получен сигнал остановки")
        except Exception as e:
            logger.error(f"❌ Ошибка мониторинга: {e}")
            raise
    
    def start(self):
        """Запуск мониторинга"""
        try:
            logger.info("=== Запуск Polymarket Factory Monitor ===")
            self.is_running = True
            
            # Настраиваем подключение
            self.setup_connection()
            
            # Настраиваем обработчики сигналов
            self._setup_signal_handlers()
            
            # Запускаем мониторинг
            self.monitor_events()
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка: {e}")
            self.stop()
            sys.exit(1)
    
    def stop(self):
        """Остановка мониторинга"""
        try:
            logger.info("⏹️ Остановка Polymarket Factory Monitor...")
            self.is_running = False
            
            if self.log_filter and self.w3:
                self.w3.eth.uninstall_filter(self.log_filter.filter_id)
                logger.info("✅ Фильтр событий удален")
            
            logger.info("=== Polymarket Factory Monitor остановлен ===")
            
        except Exception as e:
            logger.error(f"❌ Ошибка при остановке: {e}")
    
    def _setup_signal_handlers(self):
        """Настройка обработчиков сигналов"""
        def signal_handler(signum, frame):
            logger.info(f"📡 Получен сигнал {signum}")
            self.is_running = False
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)


def main():
    """Главная функция"""
    monitor = PolymarketFactoryMonitor()
    monitor.start()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Программа прервана пользователем")
    except Exception as e:
        logger.error(f"Неожиданная ошибка: {e}")
        sys.exit(1) 