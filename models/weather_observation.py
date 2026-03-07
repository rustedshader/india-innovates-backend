"""Postgres model for storing daily weather observations per city."""

from datetime import date, datetime

from sqlalchemy import String, Float, Integer, Date, DateTime, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from models.database import Base


class WeatherObservation(Base):
    """Daily weather observation for an Indian city (sourced from Open-Meteo)."""

    __tablename__ = "weather_observations"

    __table_args__ = (
        UniqueConstraint("city", "date", name="uq_weather_obs_city_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    city: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    temperature_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    temperature_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    temperature_mean: Mapped[float | None] = mapped_column(Float, nullable=True)
    apparent_temperature_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    apparent_temperature_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    precipitation_sum: Mapped[float | None] = mapped_column(Float, nullable=True)
    rain_sum: Mapped[float | None] = mapped_column(Float, nullable=True)
    snowfall_sum: Mapped[float | None] = mapped_column(Float, nullable=True)
    precipitation_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_speed_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_gusts_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    humidity_mean: Mapped[float | None] = mapped_column(Float, nullable=True)
    soil_moisture_mean: Mapped[float | None] = mapped_column(Float, nullable=True)
    et0_evapotranspiration: Mapped[float | None] = mapped_column(Float, nullable=True)
    shortwave_radiation_sum: Mapped[float | None] = mapped_column(Float, nullable=True)
    weather_code: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Anomaly z-scores (computed against climate normals)
    temp_max_zscore: Mapped[float | None] = mapped_column(Float, nullable=True)
    temp_min_zscore: Mapped[float | None] = mapped_column(Float, nullable=True)
    precip_zscore: Mapped[float | None] = mapped_column(Float, nullable=True)
    soil_moisture_zscore: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<WeatherObservation(city='{self.city}', date='{self.date}', tmax={self.temperature_max})>"
