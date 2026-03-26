"""Domain stability score model."""

from datetime import datetime
from sqlalchemy import String, Float, DateTime, JSON, func
from sqlalchemy.orm import Mapped, mapped_column
from models.database import Base


class DomainStability(Base):
    __tablename__ = "domain_stability"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    domain: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Composite instability score (0=stable, 10=crisis)
    score: Mapped[float] = mapped_column(Float, nullable=False)

    # JSON breakdown: {defense_risk, economic_fragility, climate_stress, social_tension, tech_dependency}
    components: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # Staleness penalty applied when data goes stale (prevents optimistic drift)
    staleness_penalty: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Hours since last significant event in this domain
    data_age_hours: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    def __repr__(self) -> str:
        return f"<DomainStability({self.domain}, score={self.score:.2f})>"
