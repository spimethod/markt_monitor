"""
Настройки приложения
Все конфигурации загружаются из переменных окружения
"""

import os
from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from loguru import logger


class TradingConfig(BaseSettings):
    """Торговые настройки"""

    model_config = SettingsConfigDict(env_prefix="", env_file=".env", extra="ignore")

    # Основные торговые параметры
    INITIAL_DEPOSIT_USD: float = Field(
        default=10.0, description="Начальный депозит в USDC"
    )
    POSITION_SIZE_USD: float = Field(default=1.0, description="Размер позиции в USDC")
    PROFIT_TARGET_PERCENT: float = Field(
        default=10.0, description="Целевая прибыль в %"
    )

    # Фильтры рынков
    MIN_LIQUIDITY_USD: float = Field(
        default=100.0, description="Минимальная ликвидность в USD"
    )
    TIME_WINDOW_MINUTES: int = Field(
        default=10, description="Временное окно для новых рынков"
    )
    MAX_NO_PRICE: float = Field(
        default=0.85, description="Максимальная цена NO для покупки"
    )

    # Управление рисками
    MAX_OPEN_POSITIONS: int = Field(
        default=3, description="Максимальное количество открытых позиций"
    )
    MAX_POSITION_HOURS: int = Field(
        default=24, description="Максимальное время держания позиции в часах"
    )
    STOP_LOSS_PERCENT: float = Field(default=-20.0, description="Stop-loss в %")

    # Стратегия торговли
    TRADING_STRATEGY: str = Field(
        default="conservative", description="conservative или aggressive"
    )
    POSITION_SIDE: str = Field(default="NO", description="Сторона позиции: YES или NO")

    # Настройки API ротации
    API_ROTATION_ENABLED: bool = Field(
        default=True, description="Включить ротацию API ключей"
    )
    REQUEST_DELAY_SECONDS: float = Field(
        default=0.1, description="Задержка между запросами"
    )
    
    # Интервалы мониторинга
    POSITION_MONITOR_INTERVAL_SECONDS: int = Field(
        default=10, description="Интервал проверки позиций в секундах"
    )
    
    # Дневные лимиты сделок
    MAX_DAILY_TRADES_CONSERVATIVE: int = Field(
        default=10, description="Максимум сделок в день для консервативной стратегии"
    )
    MAX_DAILY_TRADES_AGGRESSIVE: int = Field(
        default=25, description="Максимум сделок в день для агрессивной стратегии"
    )
    
    # Реальные прокси серверы (опционально)
    USE_PROXY: bool = Field(
        default=False, description="Использовать прокси серверы"
    )
    PROXY_LIST: str = Field(
        default="", description="Список прокси через запятую (http://user:pass@ip:port)"
    )
    PROXY_ROTATION_ENABLED: bool = Field(
        default=False, description="Включить ротацию прокси"
    )


class PolymarketConfig(BaseSettings):
    """Polymarket API settings."""

    model_config = SettingsConfigDict(env_prefix="", env_file=".env", extra="ignore")

    # Основные параметры подключения
    PRIVATE_KEY: str = Field(
        default="0x4f3edf983ac636a65a842ce7c78d9aa706d3b113bce9c46f30d7d21715b23b1d", 
        description="Приватный ключ кошелька (тестовый по умолчанию)"
    )
    POLYMARKET_PROXY_ADDRESS: Optional[str] = Field(
        default=None, description="Адрес proxy кошелька"
    )
    SIGNATURE_TYPE: int = Field(
        default=0, description="Тип подписи: 0=EOA, 1=Email/Magic, 2=Browser"
    )



    # API эндпоинты (стандартные значения Polymarket)
    CLOB_HOST: str = Field(
        default="https://clob.polymarket.com", description="CLOB API хост"
    )
    GAMMA_HOST: str = Field(
        default="https://gamma-api.polymarket.com", description="Gamma API хост"
    )
    WEBSOCKET_HOST: str = Field(
        default="wss://ws-subscriptions-clob.polymarket.com",
        description="WebSocket хост",
    )
    USE_WEBSOCKET: bool = Field(default=True, description="Использовать WebSocket для обновлений")
    WEBSOCKET_PING_INTERVAL: int = Field(default=20, description="Интервал ping для WebSocket в секундах")
    WEBSOCKET_PING_TIMEOUT: int = Field(default=10, description="Таймаут ping для WebSocket в секундах")
    WEBSOCKET_MAX_ATTEMPTS: int = Field(default=10, description="Максимальное количество попыток переподключения WebSocket")
    WEBSOCKET_FALLBACK_ENABLED: bool = Field(default=True, description="Включить HTTP polling fallback при отказе WebSocket")
    CHAIN_ID: int = Field(default=137, description="Polygon Chain ID (137 = Mainnet, 80001 = Mumbai)")

    # --- Subgraph Gateway ---
    THEGRAPH_API_KEY: str = Field(
        default="", description="API ключ The Graph Gateway (https://thegraph.com/studio/apikeys)"
    )
    SUBGRAPH_ID: str = Field(
        default="Bx1W4S7kDVxs9gC3s2G6DS8kdNBJNVhMviCtin2DiBp", description="ID субграфа Polymarket на The Graph"
    )


class TelegramConfig(BaseSettings):
    """Telegram bot settings."""

    model_config = SettingsConfigDict(env_prefix="", env_file=".env", extra="ignore")

    TELEGRAM_BOT_TOKEN: str = Field(default="", description="Токен Telegram бота")
    TELEGRAM_CHAT_ID: str = Field(default="", description="ID чата для уведомлений")
    TELEGRAM_ADMIN_IDS: List[str] = Field(
        default_factory=list, description="ID администраторов"
    )

    # Настройки уведомлений
    NOTIFY_NEW_MARKETS: bool = Field(
        default=True, description="Уведомления о новых рынках"
    )
    NOTIFY_TRADES: bool = Field(default=True, description="Уведомления о сделках")
    NOTIFY_PROFITS: bool = Field(default=True, description="Уведомления о прибыли")
    NOTIFY_ERRORS: bool = Field(default=True, description="Уведомления об ошибках")


class DatabaseConfig(BaseSettings):
    """Database configuration."""

    model_config = SettingsConfigDict(env_prefix="", env_file=".env", extra="ignore")

    # PostgreSQL настройки (Railway автоматически предоставляет DATABASE_URL)
    DATABASE_URL: str = Field(
        default="sqlite+aiosqlite:///./bot.db", description="URL базы данных"
    )
    DB_POOL_SIZE: int = Field(default=5, description="Размер пула соединений")
    DB_MAX_OVERFLOW: int = Field(default=10, description="Максимальный overflow пула")
    DB_ECHO: bool = Field(default=False, description="Логирование SQL запросов")


class AppConfig(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(env_prefix="", env_file=".env", extra="ignore")

    # Режим работы
    ENVIRONMENT: str = Field(
        default="production", description="Окружение: development/production"
    )
    DEBUG: bool = Field(default=False, description="Режим отладки")

    # Логирование
    LOG_LEVEL: str = Field(default="INFO", description="Уровень логирования")
    LOG_TO_FILE: bool = Field(default=True, description="Сохранять логи в файл")
    LOG_FILE_PATH: str = Field(default="logs/bot.log", description="Путь к файлу логов")

    # Временные настройки
    TIMEZONE: str = Field(default="UTC", description="Временная зона")


class Config:
    """Combined configuration."""

    def __init__(self):
        # Загружаем переменные окружения из .env файла (для локальной разработки)
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            # dotenv не установлен, продолжаем без него
            pass

        # Инициализируем конфигурации
        self.trading = TradingConfig()
        self.polymarket = PolymarketConfig()
        self.telegram = TelegramConfig()
        self.database = DatabaseConfig()
        self.app = AppConfig()

        # Настраиваем логирование
        self._setup_logging()

        # Валидируем конфигурацию
        self._validate_config()

        logger.info("Конфигурация загружена успешно")

    def _setup_logging(self):
        """Настройка системы логирования"""
        logger.remove()  # Удаляем стандартный обработчик

        # Консольный вывод
        logger.add(
            lambda msg: print(msg, end=""),
            level=self.app.LOG_LEVEL,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>",
        )

        # Файловый вывод
        if self.app.LOG_TO_FILE:
            os.makedirs(os.path.dirname(self.app.LOG_FILE_PATH), exist_ok=True)
            logger.add(
                self.app.LOG_FILE_PATH,
                level=self.app.LOG_LEVEL,
                format="{time:YYYY-MM-DD HH:mm:ss} | "
                "{level: <8} | "
                "{name}:{function}:{line} - "
                "{message}",
                rotation="1 day",
                retention="30 days",
            )

    def _validate_config(self):
        """Валидация настроек"""
        # Для продакшн среды проверяем реальный ключ
        if self.app.ENVIRONMENT == "production":
            if not self.polymarket.PRIVATE_KEY or self.polymarket.PRIVATE_KEY == "0x4f3edf983ac636a65a842ce7c78d9aa706d3b113bce9c46f30d7d21715b23b1d":
                raise ValueError("PRIVATE_KEY должен быть установлен для продакшн режима (не тестовый ключ)")

        if not self.telegram.TELEGRAM_BOT_TOKEN:
            raise ValueError("TELEGRAM_BOT_TOKEN не может быть пустым")

        if not self.telegram.TELEGRAM_CHAT_ID:
            raise ValueError("TELEGRAM_CHAT_ID не может быть пустым")

        if self.trading.POSITION_SIZE_USD <= 0:
            raise ValueError("POSITION_SIZE_USD должен быть больше 0")

        if self.trading.PROFIT_TARGET_PERCENT <= 0:
            raise ValueError("PROFIT_TARGET_PERCENT должен быть больше 0")

        if self.trading.TRADING_STRATEGY not in ["conservative", "aggressive"]:
            raise ValueError(
                "TRADING_STRATEGY должен быть 'conservative' или 'aggressive'"
            )

        if self.trading.POSITION_SIDE not in ["YES", "NO"]:
            raise ValueError("POSITION_SIDE должен быть 'YES' или 'NO'")

        logger.info("Конфигурация валидирована успешно")

    def get_strategy_params(self):
        """Получить параметры стратегии в зависимости от режима"""
        if self.trading.TRADING_STRATEGY == "conservative":
            return {
                "market_filters": {
                    "min_volume_24h": 1000,
                    "min_liquidity_usd": 500,
                    "max_age_hours": 24,
                    "min_market_age_minutes": 5,
                },
                "risk_params": {
                    "max_exposure_usd": 100,
                    "stop_loss_percent": 20,
                    "max_daily_trades": self.trading.MAX_DAILY_TRADES_CONSERVATIVE,
                },
            }
        return {
            "market_filters": {
                "min_volume_24h": 500,
                "min_liquidity_usd": 200,
                "max_age_hours": 48,
                "min_market_age_minutes": 1,
            },
            "risk_params": {
                "max_exposure_usd": 500,
                "stop_loss_percent": 10,
                "max_daily_trades": self.trading.MAX_DAILY_TRADES_AGGRESSIVE,
            },
        }

    def to_dict(self):
        """Конвертация в словарь для отладки"""
        return {
            "trading": self.trading.model_dump(),
            "polymarket": {
                **self.polymarket.model_dump(),
                "PRIVATE_KEY": "***HIDDEN***",  # Скрываем приватный ключ
                "POLYMARKET_PROXY_ADDRESS": "***HIDDEN***",  # Скрываем proxy адрес
            },
            "telegram": {
                **self.telegram.model_dump(),
                "TELEGRAM_BOT_TOKEN": "***HIDDEN***",  # Скрываем токен
            },
            "app": self.app.model_dump(),
        }


# Глобальный экземпляр конфигурации
config = Config()
