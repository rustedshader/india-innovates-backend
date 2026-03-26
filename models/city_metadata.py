from datetime import datetime
from typing import Optional

from sqlalchemy import String, Float, BigInteger, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB

from models.database import Base


class CityMetadata(Base):
    """Comprehensive city metadata for weather analysis and geocoding."""

    __tablename__ = "city_metadata"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    city_name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    country: Mapped[str] = mapped_column(String(100), default="India", nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    zone: Mapped[str] = mapped_column(String(20), nullable=False)  # plains, coastal, hills
    state: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    elevation_meters: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    population: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    is_india_seed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    extra_metadata: Mapped[dict] = mapped_column(JSONB, default={}, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<CityMetadata(city='{self.city_name}', zone='{self.zone}', lat={self.latitude}, lon={self.longitude})>"
