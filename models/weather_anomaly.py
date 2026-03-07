"""Postgres model for detected weather anomaly events."""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import String, Float, Text, Date, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from models.database import Base


class WeatherAnomalyRecord(Base):
    """A detected weather anomaly event (heat wave, flood, drought, etc.)."""

    __tablename__ = "weather_anomalies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    city: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    anomaly_type: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True,
        doc="heat_wave | cold_wave | extreme_rain | drought | cyclone_proxy | unusual_warmth | monsoon_deficit",
    )
    severity: Mapped[str] = mapped_column(
        String(32), nullable=False,
        doc="warning | severe | extreme",
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    peak_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    z_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<WeatherAnomalyRecord(city='{self.city}', type='{self.anomaly_type}', "
            f"severity='{self.severity}', start='{self.start_date}')>"
        )
