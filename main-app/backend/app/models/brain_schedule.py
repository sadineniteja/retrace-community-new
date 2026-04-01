"""
Brain schedule model — recurring task schedules for a Brain.

Reuses the scheduling patterns from SOP (schedule_type, schedule_config)
and integrates with APScheduler via the brain_scheduler service.
"""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import String, DateTime, Text, JSON, ForeignKey, Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class BrainSchedule(Base):
    """A recurring schedule that generates tasks for a Brain."""

    __tablename__ = "brain_schedules"

    schedule_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    brain_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("brains.brain_id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # What to do
    task_type: Mapped[str] = mapped_column(String(50), nullable=False, default="general")
    task_instructions: Mapped[str] = mapped_column(Text, nullable=False, default="")
    task_config: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    # When to do it (same format as SOP schedule_config)
    schedule_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="daily"
    )  # once | interval | daily | weekly | monthly | cron
    schedule_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    next_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    run_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    brain = relationship("Brain", back_populates="schedules")

    def to_dict(self) -> dict:
        return {
            "schedule_id": self.schedule_id,
            "brain_id": self.brain_id,
            "name": self.name,
            "description": self.description,
            "task_type": self.task_type,
            "task_instructions": self.task_instructions,
            "task_config": self.task_config,
            "schedule_type": self.schedule_type,
            "schedule_config": self.schedule_config,
            "timezone": self.timezone,
            "is_active": self.is_active,
            "next_run_at": self.next_run_at.isoformat() if self.next_run_at else None,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "run_count": self.run_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
