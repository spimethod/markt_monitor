"""
Менеджер базы данных для работы с позициями
"""
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

        if not config.database.DATABASE_URL:
            logger.error("DATABASE_URL не настроен. База данных не будет использоваться.")

    async def initialize(self) -> bool:
        """Инициализация подключения к базе данных"""
        if self._initialized:
            return True
        
        db_url = config.database.DATABASE_URL
        if not db_url:
            return False

        try:
            if db_url.startswith("postgres://"):
                db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)

            self.engine = create_async_engine(db_url, echo=False, pool_pre_ping=True, pool_recycle=300)
            self.Session = async_sessionmaker(bind=self.engine, class_=AsyncSession, expire_on_commit=False)

            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            self._initialized = True
            logger.info("База данных успешно инициализирована")
            return True
        except Exception as e:
            logger.error(f"Ошибка инициализации базы данных: {e}")
            self._initialized = False
            return False

    async def close(self):
        """Закрытие подключения к базе данных"""
        if self.engine:
            await self.engine.dispose()
            logger.info("Подключение к базе данных закрыто")

    async def _get_session(self) -> Optional[AsyncSession]:
        """Получение сессии. Если сессии нет, пытается инициализировать подключение."""
        if not self._initialized:
            await self.initialize()
        
        if self.Session:
            return self.Session()
        return None

    async def save_position(self, position_data: Dict[str, Any]) -> bool:
        """Сохранение позиции в базу данных"""
        session = await self._get_session()
        if not session:
            return False
        async with session:
            try:
                position = Position(**position_data)
                session.add(position)
                await session.commit()
                logger.info(f"Позиция {position_data.get('id')} сохранена в БД")
                return True
            except Exception as e:
                logger.error(f"Ошибка сохранения позиции: {e}")
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
            return False
        async with session:
            try:
                values = {"status": "closed", "close_reason": close_reason, "closed_at": datetime.utcnow(), "updated_at": datetime.utcnow()}
                if realized_pnl is not None:
                    values["realized_pnl"] = realized_pnl
                await session.execute(update(Position).where(Position.id == position_id).values(**values))
                await session.commit()
                return True
            except Exception as e:
                logger.error(f"Ошибка закрытия позиции: {e}")
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