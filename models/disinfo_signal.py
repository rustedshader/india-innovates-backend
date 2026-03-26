"""Disinformation signal model."""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Float, DateTime, JSON, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from models.database import Base


class DisinfoSignal(Base):
    __tablename__ = "disinfo_signals"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Type: coordinated_narrative | sentiment_manipulation | source_network | targeted_operation
    signal_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Severity: high | medium | low
    severity: Mapped[str] = mapped_column(String(8), nullable=False, default="medium")

    # Confidence score (0.0 – 1.0)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)

    # Actor attribution (e.g. "state-sponsored", "domestic political", "unknown")
    actor_attribution: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    # Target entity and domain
    target_entity: Mapped[Optional[str]] = mapped_column(String(256), nullable=True, index=True)
    target_domain: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Narrative cluster details
    cluster_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    narrative_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    coordination_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Evidence article URLs (JSON list)
    evidence_articles: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    # Involved sources
    flagged_sources: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<DisinfoSignal({self.signal_type}, {self.target_entity}, conf={self.confidence:.2f})>"
