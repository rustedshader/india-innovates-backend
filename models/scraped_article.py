from datetime import datetime

from sqlalchemy import String, Text, DateTime, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column

from models.database import Base


class ScrapedArticle(Base):
    """Stores already-scraped news article URLs and metadata."""

    __tablename__ = "scraped_articles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(String(2048), unique=True, nullable=False, index=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(1024), nullable=False)
    source: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    pub_date: Mapped[str] = mapped_column(String(128), default="")
    guid: Mapped[str] = mapped_column(String(512), default="")

    full_text: Mapped[str] = mapped_column(Text, default="")
    authors: Mapped[str] = mapped_column(Text, default="")  # JSON-encoded list
    top_image: Mapped[str] = mapped_column(String(2048), default="")

    is_content_extracted: Mapped[bool] = mapped_column(Boolean, default=False)
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<ScrapedArticle(id={self.id}, source='{self.source}', title='{self.title[:50]}...')>"
