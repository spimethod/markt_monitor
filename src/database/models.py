"""
Модели базы данных для хранения торговых позиций
"""
# pylint: disable=too-few-public-methods,too-many-instance-attributes,invalid-name

from datetime import datetime
from typing import Dict, Any, Optional

from sqlalchemy import (
    String, Float, DateTime, Integer, Text, func
)
from sqlalchemy.orm import declarative_base, Mapped, mapped_column

Base: Any = declarative_base()

class Position(Base):
    """Модель торговой позиции"""
    __tablename__ = "positions"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    token_id: Mapped[str] = mapped_column(String(255), nullable=False)
    market_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    user_address: Mapped[str] = mapped_column(String(255), nullable=False)
    side: Mapped[str] = mapped_column(String(50), nullable=False)
    size: Mapped[float] = mapped_column(Float, nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    current_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target_profit: Mapped[float] = mapped_column(Float, nullable=False, default=10.0)
    stop_loss: Mapped[float] = mapped_column(Float, nullable=False, default=-20.0)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="open")
    close_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    realized_pnl: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    unrealized_pnl: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    market_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def to_dict(self) -> Dict[str, Any]:
        """Конвертация в словарь"""
        d = {}
        for column in self.__table__.columns:
            value = getattr(self, column.name)
            if isinstance(value, datetime):
                d[column.name] = value.isoformat()
            else:
                d[column.name] = value
        return d

class TradingStats(Base):
    """Модель для хранения торговой статистики"""
    __tablename__ = "trading_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    daily_trades: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_trades: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    successful_trades: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_profit: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    daily_profit: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    markets_analyzed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    markets_filtered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    def to_dict(self) -> Dict[str, Any]:
        """Конвертация в словарь"""
        d = {}
        for column in self.__table__.columns:
            value = getattr(self, column.name)
            if isinstance(value, datetime):
                d[column.name] = value.isoformat()
            else:
                d[column.name] = value
        return d 