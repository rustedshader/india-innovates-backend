from datetime import datetime

from sqlalchemy import String, Float, Boolean, Text, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from models.database import Base


class SourceConfig(Base):
    """Per-source credibility scores used by NewsPriorityAgent for cluster rep selection."""

    __tablename__ = "source_config"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    credibility_score: Mapped[float] = mapped_column(Float, default=0.70, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<SourceConfig(source='{self.source_name}', credibility={self.credibility_score})>"
