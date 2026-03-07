"""Postgres model for 30-year climate normals per city/month/variable."""

from datetime import datetime

from sqlalchemy import String, Float, Integer, DateTime, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from typing import Optional

from models.database import Base


class ClimateNormal(Base):
    """Monthly climate normals (1991-2020 ERA5) used as baseline for anomaly detection."""

    __tablename__ = "climate_normals"

    __table_args__ = (
        UniqueConstraint("city", "month", "variable", name="uq_climate_normal"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    city: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    month: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-12
    variable: Mapped[str] = mapped_column(String(64), nullable=False)
    mean: Mapped[float] = mapped_column(Float, nullable=False)
    std: Mapped[float] = mapped_column(Float, nullable=False)
    p5: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    p25: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    p75: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    p95: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<ClimateNormal(city='{self.city}', month={self.month}, "
            f"var='{self.variable}', mean={self.mean:.1f}±{self.std:.1f})>"
        )
