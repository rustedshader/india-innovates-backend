from datetime import datetime
from typing import List

from sqlalchemy import String, Float, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB

from models.database import Base


class EntityTypeDomainMapping(Base):
    """Mapping of entity types to domains (e.g., Person -> geopolitics)."""

    __tablename__ = "entity_type_domain_mappings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    primary_domain: Mapped[str] = mapped_column(String(50), nullable=False)
    secondary_domains: Mapped[List[str]] = mapped_column(JSONB, default=[], nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<EntityTypeDomainMapping(type='{self.entity_type}', domain='{self.primary_domain}')>"
