"""Postgres model for entity state history.

Each row represents one attribute-value pair for an entity
during a specific time window.  When a new article contradicts
a current state, the old row gets `valid_to` set and a new row
is inserted.  This gives full temporal provenance for the graph.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Float, DateTime, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from models.database import Base


class EntityState(Base):
    __tablename__ = "entity_states"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # The graph entity this state belongs to
    entity_name: Mapped[str] = mapped_column(String(256), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False, default="")

    # What attribute changed (e.g. "diplomatic_status", "oil_price_trend", "leadership")
    attribute: Mapped[str] = mapped_column(String(128), nullable=False)

    # The state value (e.g. "sanctions_imposed", "rising", "Modi")
    value: Mapped[str] = mapped_column(String(512), nullable=False)

    # Raw temporal marker from extraction ("2025-03", "ongoing", etc.)
    temporal_marker: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Confidence from relation extraction (0.0–1.0)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)

    # Time window this state is valid
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Provenance
    source_article_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    source_article_title: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        # Fast lookups for timeline queries
        Index("ix_entity_states_entity_attr", "entity_name", "attribute"),
        Index("ix_entity_states_valid_from", "valid_from"),
        Index("ix_entity_states_valid_to", "valid_to"),
    )

    @property
    def is_current(self) -> bool:
        return self.valid_to is None

    def __repr__(self) -> str:
        status = "current" if self.is_current else f"until {self.valid_to}"
        return (
            f"<EntityState({self.entity_name!r}, "
            f"{self.attribute}={self.value!r}, {status})>"
        )
