"""Postgres model for caching LLM-generated domain relevance weights.

Weights are generated once per domain per day by asking the LLM to score
entity types and relation types for domain relevance, based on a sample of
what the knowledge graph actually contains.
"""

from datetime import datetime

from sqlalchemy import String, Text, DateTime, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from models.database import Base


class DomainWeightCache(Base):
    """Caches LLM-generated domain relevance weights (1 row per domain per day)."""

    __tablename__ = "domain_weight_cache"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    domain: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    cache_date: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD
    entity_weights: Mapped[str] = mapped_column(Text, nullable=False)    # JSON dict
    relation_weights: Mapped[str] = mapped_column(Text, nullable=False)  # JSON dict
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("domain", "cache_date", name="uq_domain_cache_date"),
    )

    def __repr__(self) -> str:
        return f"<DomainWeightCache(domain='{self.domain}', date='{self.cache_date}')>"
