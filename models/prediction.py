"""Prediction model with explainability and calibration tracking."""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Float, DateTime, JSON, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from models.database import Base


class Prediction(Base):
    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # The prediction text
    prediction_text: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    horizon: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # e.g. "30d", "6m"

    # Overall confidence (0.0–1.0)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)

    # Decomposed confidence scores (JSON)
    # {data_confidence, causal_confidence, temporal_confidence, source_diversity}
    confidence_components: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Source attribution (list of article URLs + titles)
    source_articles: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    # The graph path backing this prediction (list of entity→relation links)
    reasoning_chain: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    # Neo4j Cypher path that produced this prediction
    graph_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Entities involved
    entities: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Outcome tracking for calibration
    outcome: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)  # "correct" | "incorrect" | "partial"
    outcome_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    outcome_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<Prediction(conf={self.confidence:.2f}, {self.prediction_text[:60]!r})>"
