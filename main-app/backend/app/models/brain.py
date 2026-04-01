"""
Brain model — an autonomous AI employee.

Each Brain is configured from a template, goes through a setup interview,
connects to external accounts, and then executes tasks autonomously.
"""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import String, DateTime, Text, JSON, ForeignKey, Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class Brain(Base):
    """An autonomous AI employee (Brain)."""

    __tablename__ = "brains"

    brain_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    tenant_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("tenants.tenant_id"), nullable=True,
    )
    template_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("brain_templates.template_id"), nullable=True,
    )

    # Identity
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    brain_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="custom"
    )  # job_searcher | trader | social_media | coder | personal_finance | custom
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    icon: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    color: Mapped[Optional[str]] = mapped_column(String(7), nullable=True)

    # Setup interview state
    setup_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )  # pending | interview | ready | error
    setup_step: Mapped[int] = mapped_column(Integer, default=0)
    setup_answers: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # System prompt built from template + setup answers
    system_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Autonomy level
    autonomy_level: Mapped[str] = mapped_column(
        String(20), nullable=False, default="supervised"
    )  # supervised | semi_auto | full_auto

    # Runtime state
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="inactive"
    )  # inactive | active | paused | error
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    last_active_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Daily limits
    max_daily_tasks: Mapped[int] = mapped_column(Integer, default=50)
    max_daily_cost_cents: Mapped[int] = mapped_column(Integer, default=500)
    tasks_today: Mapped[int] = mapped_column(Integer, default=0)
    cost_today_cents: Mapped[int] = mapped_column(Integer, default=0)

    # Brain-type-specific configuration
    config_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    connected_accounts = relationship(
        "ConnectedAccount", back_populates="brain", cascade="all, delete-orphan"
    )
    tasks = relationship(
        "BrainTask", back_populates="brain", cascade="all, delete-orphan"
    )
    schedules = relationship(
        "BrainSchedule", back_populates="brain", cascade="all, delete-orphan"
    )
    monitors = relationship(
        "BrainMonitor", back_populates="brain", cascade="all, delete-orphan"
    )
    activities = relationship(
        "BrainActivity", back_populates="brain", cascade="all, delete-orphan"
    )
    pipeline_items = relationship(
        "PipelineItem", back_populates="brain", cascade="all, delete-orphan"
    )

    def to_dict(self) -> dict:
        return {
            "brain_id": self.brain_id,
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "template_id": self.template_id,
            "name": self.name,
            "brain_type": self.brain_type,
            "description": self.description,
            "icon": self.icon,
            "color": self.color,
            "setup_status": self.setup_status,
            "setup_step": self.setup_step,
            "setup_answers": self.setup_answers,
            "autonomy_level": self.autonomy_level,
            "status": self.status,
            "is_active": self.is_active,
            "last_active_at": self.last_active_at.isoformat() if self.last_active_at else None,
            "max_daily_tasks": self.max_daily_tasks,
            "max_daily_cost_cents": self.max_daily_cost_cents,
            "tasks_today": self.tasks_today,
            "cost_today_cents": self.cost_today_cents,
            "config": self.config_json or {},
            "metadata": self.metadata_json or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
