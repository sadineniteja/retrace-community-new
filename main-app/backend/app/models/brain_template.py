"""
Brain template model — predefined brain archetypes (job_searcher, trader, etc.).

Each template defines the setup interview questions, system prompt template,
required/optional connected accounts, available tools, and default schedules/monitors.
"""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import String, DateTime, Text, JSON, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class BrainTemplate(Base):
    """Predefined brain template (job_searcher, trader, etc.)."""

    __tablename__ = "brain_templates"

    template_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    slug: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    icon: Mapped[str] = mapped_column(String(50), nullable=False, default="brain")
    color: Mapped[str] = mapped_column(String(7), nullable=False, default="#6366f1")
    category: Mapped[str] = mapped_column(String(50), nullable=False, default="general")

    # Interview questions (ordered list of question dicts)
    # e.g. [{"key": "target_role", "question": "What role?", "type": "text", "required": true}, ...]
    interview_questions: Mapped[dict] = mapped_column(JSON, nullable=False, default=list)

    # System prompt template with {setup_answers.xyz} placeholders
    system_prompt_template: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Default config for this brain type
    default_config: Mapped[dict] = mapped_column(JSON, default=dict)

    # Required / optional connected account providers
    required_accounts: Mapped[dict] = mapped_column(JSON, default=list)
    optional_accounts: Mapped[dict] = mapped_column(JSON, default=list)

    # Available tools for this brain type
    available_tools: Mapped[dict] = mapped_column(JSON, default=list)

    # Default schedules and monitors created when brain activates
    default_schedules: Mapped[dict] = mapped_column(JSON, default=list)
    default_monitors: Mapped[dict] = mapped_column(JSON, default=list)

    is_builtin: Mapped[bool] = mapped_column(Boolean, default=True)
    is_published: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "template_id": self.template_id,
            "slug": self.slug,
            "name": self.name,
            "description": self.description,
            "icon": self.icon,
            "color": self.color,
            "category": self.category,
            "interview_questions": self.interview_questions,
            "required_accounts": self.required_accounts,
            "optional_accounts": self.optional_accounts,
            "available_tools": self.available_tools,
            "default_schedules": self.default_schedules,
            "default_monitors": self.default_monitors,
            "is_builtin": self.is_builtin,
            "is_published": self.is_published,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
