"""
Менеджер базы данных для работы с позициями
"""
import asyncio
from datetime import datetime
from typing import List, Optional, Dict, Any
from loguru import logger

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select, update

from src.config.settings import config
from src.database.models import Base, Position


class DatabaseManager:
    """Менеджер для работы с базой данных позиций"""

    def __init__(self):
        """Инициализация менеджера базы данных"""
        self._initialized = False
        self.engine: Optional[Any] = None
        self.Session: Optional[async_sessionmaker[AsyncSession]] = None
        self._using_sqlite_fallback = False

        if not config.database.DATABASE_URL:
            logger.error("DATABASE_URL не настроен. База данных не будет использоваться.")

    async def initialize(self) -> bool:
        """Инициализация подключения к базе данных с retry и fallback"""
        if self._initialized:
            return True
        
        db_url = config.database.DATABASE_URL
        if not db_url:
            return False

        # Проверяем тип базы данных
        is_postgres = db_url.startswith(("postgres://", "postgresql://"))
        
        if is_postgres:
            # Пробуем PostgreSQL с таймаутами и retry
            success = await self._initialize_postgres(db_url)
            if success:
                return True
            
            # Fallback на SQLite если PostgreSQL не работает
            logger.warning("PostgreSQL недоступен, переключаемся на SQLite fallback")
            return await self._initialize_sqlite_fallback()
        else:
            # Инициализируем SQLite напрямую
            return await self._initialize_sqlite(db_url)

    async def _initialize_postgres(self, db_url: str, max_retries: int = 3) -> bool:
        """Инициализация PostgreSQL с retry механизмом"""
        # Обрабатываем различные форматы PostgreSQL URL
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif db_url.startswith("postgresql://") and not db_url.startswith("postgresql+asyncpg://"):
            db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        
        for attempt in range(max_retries):
            try:
                logger.info(f"Попытка {attempt + 1}/{max_retries} подключения к PostgreSQL: {db_url[:30]}...")

                # Создаем engine с таймаутами
                self.engine = create_async_engine(
                    db_url, 
                    echo=False, 
                    pool_pre_ping=True, 
                    pool_recycle=300,
                    connect_args={
                        "command_timeout": 10,  # 10 секунд на команду
                        "server_settings": {
                            "application_name": "polymarket_bot",
                        }
                    }
                )
                
                self.Session = async_sessionmaker(bind=self.engine, class_=AsyncSession, expire_on_commit=False)

                # Проверяем подключение с таймаутом
                async with asyncio.timeout(15):  # 15 секунд на подключение и создание таблиц
                    async with self.engine.begin() as conn:
                        await conn.run_sync(Base.metadata.create_all)

                self._initialized = True
                logger.info("PostgreSQL база данных успешно инициализирована")
                return True
                
            except asyncio.TimeoutError:
                logger.warning(f"Таймаут подключения к PostgreSQL (попытка {attempt + 1}/{max_retries})")
                if self.engine:
                    await self.engine.dispose()
                    self.engine = None
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
            except Exception as e:
                logger.warning(f"Ошибка подключения к PostgreSQL (попытка {attempt + 1}/{max_retries}): {e}")
                if self.engine:
                    await self.engine.dispose()
                    self.engine = None
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff

        return False

    async def _initialize_sqlite_fallback(self) -> bool:
        """Fallback на SQLite если PostgreSQL недоступен"""
        sqlite_url = "sqlite+aiosqlite:///./bot.db"
        logger.info("Инициализируем SQLite fallback базу данных...")
        self._using_sqlite_fallback = True
        return await self._initialize_sqlite(sqlite_url)

    async def _initialize_sqlite(self, db_url: str) -> bool:
        """Инициализация SQLite базы данных"""
        try:
            logger.info(f"Подключение к SQLite: {db_url}")

            self.engine = create_async_engine(db_url, echo=False)
            self.Session = async_sessionmaker(bind=self.engine, class_=AsyncSession, expire_on_commit=False)

            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            self._initialized = True
            logger.info("SQLite база данных успешно инициализирована")
            return True
        except Exception as e:
            logger.error(f"Ошибка инициализации SQLite: {e}")
            self._initialized = False
            return False

    async def close(self):
        """Закрытие подключения к базе данных"""
        if self.engine:
            await self.engine.dispose()
            logger.info("Подключение к базе данных закрыто")

    async def _get_session(self) -> Optional[AsyncSession]:
        """Получение сессии базы данных"""
        if not self._initialized:
            await self.initialize()
        
        if self.Session:
            return self.Session()
        return None

    async def save_position(self, position_data: Dict[str, Any]) -> bool:
        """Сохранение позиции в базу данных"""
        session = await self._get_session()
        if not session:
            logger.error("Не удалось получить сессию БД для сохранения позиции")
            return False
        async with session:
            try:
                logger.info(f"Сохранение позиции в БД: {position_data.get('id')} - {position_data.get('market_name', 'N/A')}")
                position = Position(**position_data)
                session.add(position)
                await session.commit()
                logger.info(f"✅ Позиция {position_data.get('id')} успешно сохранена в БД")
                return True
            except Exception as e:
                logger.error(f"❌ Ошибка сохранения позиции {position_data.get('id')}: {e}")
                await session.rollback()
                return False

    async def get_open_positions(self) -> List[Dict[str, Any]]:
        """Получение всех открытых позиций"""
        session = await self._get_session()
        if not session:
            return []
        async with session:
            try:
                result = await session.execute(select(Position).where(Position.status == "open"))
                return [pos.to_dict() for pos in result.scalars().all()]
            except Exception as e:
                logger.error(f"Ошибка получения позиций: {e}")
                return []
    
    async def update_position_price(self, position_id: str, current_price: Optional[float]) -> bool:
        """Обновление цены для позиции"""
        session = await self._get_session()
        if not session:
            return False
        async with session:
            try:
                await session.execute(update(Position).where(Position.id == position_id).values(current_price=current_price, updated_at=datetime.utcnow()))
                await session.commit()
                return True
            except Exception as e:
                logger.error(f"Ошибка обновления цены: {e}")
                return False

    async def close_position(self, position_id: str, close_reason: str, realized_pnl: Optional[float]) -> bool:
        """Закрытие позиции в базе данных"""
        session = await self._get_session()
        if not session:
            logger.error("Не удалось получить сессию БД для закрытия позиции")
            return False
        async with session:
            try:
                logger.info(f"Закрытие позиции в БД: {position_id} - {close_reason}")
                values = {"status": "closed", "close_reason": close_reason, "closed_at": datetime.utcnow(), "updated_at": datetime.utcnow()}
                if realized_pnl is not None:
                    values["realized_pnl"] = realized_pnl
                await session.execute(update(Position).where(Position.id == position_id).values(**values))
                await session.commit()
                logger.info(f"✅ Позиция {position_id} успешно закрыта в БД")
                return True
            except Exception as e:
                logger.error(f"❌ Ошибка закрытия позиции {position_id}: {e}")
                await session.rollback()
                return False

    async def get_position_by_id(self, position_id: str) -> Optional[Dict[str, Any]]:
        """Получение позиции по ID"""
        session = await self._get_session()
        if not session:
            return None
        async with session:
            try:
                res = await session.execute(select(Position).where(Position.id == position_id))
                pos = res.scalar_one_or_none()
                return pos.to_dict() if pos else None
            except Exception as e:
                logger.error(f"Ошибка получения позиции: {e}")
                return None 

    def get_database_status(self) -> Dict[str, Any]:
        """Получение статуса базы данных"""
        return {
            "initialized": self._initialized,
            "using_sqlite_fallback": self._using_sqlite_fallback,
            "engine_type": "PostgreSQL" if not self._using_sqlite_fallback and self._initialized else "SQLite" if self._initialized else "None"
        } 