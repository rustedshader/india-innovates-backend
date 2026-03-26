from datetime import datetime
from typing import Optional

from sqlalchemy import String, Float, Integer, Boolean, DateTime, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from models.database import Base


class ScoringWeight(Base):
    """Configurable and learnable scoring formula weights."""

    __tablename__ = "scoring_weights"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    weight_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)  # domain_multiplier, formula_component, etc.
    component_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    weight_value: Mapped[float] = mapped_column(Float, nullable=False)
    last_calibrated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    performance_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # track accuracy
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        UniqueConstraint('weight_type', 'component_name', 'version', name='uq_scoring_weight'),
    )

    def __repr__(self) -> str:
        return f"<ScoringWeight(type='{self.weight_type}', component='{self.component_name}', value={self.weight_value}, version={self.version})>"
