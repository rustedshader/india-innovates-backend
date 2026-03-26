from datetime import datetime
from typing import Optional

from sqlalchemy import String, Float, Integer, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from models.database import Base


class IndiaSeedEntity(Base):
    """Dynamically discovered India-related entities from knowledge graph."""

    __tablename__ = "india_seed_entities"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    entity_name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    entity_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    relevance_score: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    connection_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    is_core: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    discovered_via: Mapped[str] = mapped_column(String(50), nullable=False, default="graph_traversal")  # graph_traversal, manual, external_api

    def __repr__(self) -> str:
        return f"<IndiaSeedEntity(name='{self.entity_name}', type='{self.entity_type}', relevance={self.relevance_score})>"
