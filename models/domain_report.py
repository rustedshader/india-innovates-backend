"""Postgres model for storing generated domain reports."""

from datetime import datetime

from sqlalchemy import String, Text, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from models.database import Base


class DomainReport(Base):
    """Stores auto-generated intelligence reports per domain."""

    __tablename__ = "domain_reports"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    domain: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    date_range: Mapped[str] = mapped_column(String(16), nullable=False, default="7d")
    content: Mapped[str] = mapped_column(Text, nullable=False)  # JSON report
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<DomainReport(id={self.id}, domain='{self.domain}', generated_at='{self.generated_at}')>"
