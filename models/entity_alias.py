from datetime import datetime

from sqlalchemy import String, Float, DateTime, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from typing import Optional

from models.database import Base


class EntityAlias(Base):
    """Persistent merge table for entity resolution.
    Maps (alias, context_type) → canonical entity name.

    context_type gates when an alias fires:
      - NULL  → always apply (type-independent, e.g. "usa" → "United States")
      - "Country" → only when entity was tagged as Country (e.g. "moscow" → "Russia")
    """

    __tablename__ = "entity_aliases"
    __table_args__ = (
        UniqueConstraint("alias", "context_type", name="uq_alias_context"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    alias: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    canonical: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    context_type: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, default=None,
        doc="If set, alias only fires when entity type matches. NULL = always.",
    )
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    resolved_by: Mapped[str] = mapped_column(String(32), default="tier1")  # seed, tier1, tier2, tier3, graph
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        ctx = f" [{self.context_type}]" if self.context_type else ""
        return f"<EntityAlias('{self.alias}' → '{self.canonical}'{ctx}, {self.resolved_by})>"
