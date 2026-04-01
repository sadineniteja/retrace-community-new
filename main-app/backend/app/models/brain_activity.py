"""
Brain activity log — immutable audit trail of everything a Brain does.

Every significant action (task started, email sent, job applied, trade executed)
creates an activity entry. This powers the activity feed in the UI.
"""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import String, DateTime, Text, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class BrainActivity(Base):
    """Immutable activity log entry for a Brain."""

    __tablename__ = "brain_activities"

    activity_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    brain_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("brains.brain_id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    task_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("brain_tasks.task_id", ondelete="SET NULL"),
        nullable=True, index=True,
    )

    activity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # task_started | task_completed | task_failed | approval_requested |
    # approval_granted | approval_denied | monitor_triggered | account_connected |
    # account_disconnected | schedule_created | browser_action | message_sent |
    # search_performed | application_submitted | trade_executed | post_published

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Structured detail data
    detail_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    severity: Mapped[str] = mapped_column(String(10), default="info")
    # info | success | warning | error

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    brain = relationship("Brain", back_populates="activities")

    def to_dict(self) -> dict:
        return {
            "activity_id": self.activity_id,
            "brain_id": self.brain_id,
            "task_id": self.task_id,
            "activity_type": self.activity_type,
            "title": self.title,
            "description": self.description,
            "detail": self.detail_json,
            "severity": self.severity,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
