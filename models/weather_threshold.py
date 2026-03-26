from datetime import datetime
from typing import Optional

from sqlalchemy import String, Float, Integer, Boolean, DateTime, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from models.database import Base


class WeatherThreshold(Base):
    """Weather anomaly detection thresholds (city/zone/season specific)."""

    __tablename__ = "weather_thresholds"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    zone: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # plains, coastal, hills
    season: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # winter, summer, monsoon, post_monsoon
    threshold_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # heat_wave, cold_wave, heavy_rain, etc.
    threshold_value: Mapped[float] = mapped_column(Float, nullable=False)
    departure_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    consecutive_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint('city', 'zone', 'season', 'threshold_type', name='uq_weather_threshold'),
    )

    def __repr__(self) -> str:
        return f"<WeatherThreshold(city='{self.city}', zone='{self.zone}', type='{self.threshold_type}', value={self.threshold_value})>"
