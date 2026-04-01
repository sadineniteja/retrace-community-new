"""
Brain task model — a single unit of work performed by a Brain.

Tasks are created by schedules, monitors, user requests, or chained from
other tasks. They go through an approval flow if required, then execute
via the LangGraph agent engine.
"""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import String, DateTime, Text, JSON, ForeignKey, Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class BrainTask(Base):
    """A single task executed by a Brain."""

    __tablename__ = "brain_tasks"

    task_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    brain_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("brains.brain_id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    schedule_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("brain_schedules.schedule_id", ondelete="SET NULL"),
        nullable=True,
    )
    parent_task_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("brain_tasks.task_id", ondelete="SET NULL"),
        nullable=True,
    )
    pipeline_item_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("pipeline_items.item_id", ondelete="SET NULL"),
        nullable=True,
    )

    # Task definition
    task_type: Mapped[str] = mapped_column(String(50), nullable=False, default="general")
    # general | search | apply | message | monitor | trade | post | review | custom
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    instructions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Execution state
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )  # pending | awaiting_approval | running | completed | failed | cancelled
    priority: Mapped[int] = mapped_column(Integer, default=5)  # 1=highest, 10=lowest

    trigger: Mapped[str] = mapped_column(
        String(20), nullable=False, default="manual"
    )  # manual | scheduled | monitor | chain | user_chat

    # Approval flow
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    approved_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)

    # Execution tracking
    thread_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    iterations: Mapped[int] = mapped_column(Integer, default=0)
    max_iterations: Mapped[int] = mapped_column(Integer, default=25)

    # Results
    result_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    result_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Token/cost tracking
    token_usage: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    cost_cents: Mapped[int] = mapped_column(Integer, default=0)

    # Timing
    queued_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    # Relationships
    brain = relationship("Brain", back_populates="tasks")
    sub_tasks = relationship(
        "BrainTask", backref="parent_task", remote_side="BrainTask.task_id",
    )

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "brain_id": self.brain_id,
            "schedule_id": self.schedule_id,
            "parent_task_id": self.parent_task_id,
            "pipeline_item_id": self.pipeline_item_id,
            "task_type": self.task_type,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "priority": self.priority,
            "trigger": self.trigger,
            "requires_approval": self.requires_approval,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "iterations": self.iterations,
            "result_summary": self.result_summary,
            "result_data": self.result_data,
            "error": self.error,
            "cost_cents": self.cost_cents,
            "queued_at": self.queued_at.isoformat() if self.queued_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata_json or {},
        }
