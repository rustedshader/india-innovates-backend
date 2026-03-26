from datetime import datetime
from typing import List

from sqlalchemy import String, Float, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB

from models.database import Base


class CoordinationPattern(Base):
    """Detected disinformation coordination patterns across sources."""

    __tablename__ = "coordination_patterns"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    pattern_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    source_cluster: Mapped[List[str]] = mapped_column(JSONB, nullable=False)  # array of sources
    time_window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    time_window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    coordination_score: Mapped[float] = mapped_column(Float, nullable=False)  # 0.0-1.0
    message_similarity: Mapped[float] = mapped_column(Float, nullable=False)  # semantic similarity
    timing_correlation: Mapped[float] = mapped_column(Float, nullable=False)  # publication timing
    network_density: Mapped[float] = mapped_column(Float, nullable=False)  # source interconnectedness
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<CoordinationPattern(pattern_id='{self.pattern_id}', score={self.coordination_score}, sources={len(self.source_cluster)})>"
