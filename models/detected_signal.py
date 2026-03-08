"""Postgres model for persisted anomaly signals.

Signals are written by the background signal_worker and read by the API.
No computation happens at request time.
"""

from datetime import datetime

from sqlalchemy import String, Float, Integer, DateTime, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from models.database import Base


class DetectedSignal(Base):
    __tablename__ = "detected_signals"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # One of: "entity_spike" | "new_entity" | "topic_spike"
    signal_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # "high" or "medium"
    severity: Mapped[str] = mapped_column(String(8), nullable=False)

    # Populated for entity_spike / new_entity; empty for topic_spike
    entity_name: Mapped[str] = mapped_column(String(256), default="")
    entity_type: Mapped[str] = mapped_column(String(64), default="")

    # Populated for topic_spike; empty for entity signals
    cluster_id: Mapped[str] = mapped_column(String(64), default="")
    cluster_label: Mapped[str] = mapped_column(String(256), default="")

    domain: Mapped[str] = mapped_column(String(64), default="")

    spike_ratio: Mapped[float] = mapped_column(Float, nullable=False)
    current_count: Mapped[int] = mapped_column(Integer, nullable=False)
    baseline_count: Mapped[float] = mapped_column(Float, nullable=False)

    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    # Signal auto-expires — API filters WHERE expires_at > now()
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    # Prevent duplicate signals in the same detection run for the same subject
    __table_args__ = (
        UniqueConstraint(
            "signal_type", "entity_name", "cluster_id", "detected_at",
            name="uq_signal_subject_detected_at",
        ),
    )

    def __repr__(self) -> str:
        subject = self.entity_name or self.cluster_label
        return f"<DetectedSignal({self.signal_type}, '{subject}', ratio={self.spike_ratio:.1f})>"
