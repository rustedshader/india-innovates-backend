"""Policy brief model."""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, DateTime, JSON, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from models.database import Base


class PolicyBrief(Base):
    __tablename__ = "policy_briefs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # intelligence_summary | policy_brief | options_memo | sitrep
    brief_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    domain: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    topic: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

    # Structured content (JSON): sections vary by brief_type
    content: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # Markdown-rendered version for quick consumption
    markdown_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Source references
    sources: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    # Entities referenced in the brief
    entities: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    # For sitreps: the date range covered
    period_from: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    period_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<PolicyBrief({self.brief_type}, {self.domain}, {self.created_at})>"
