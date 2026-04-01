"""
Pipeline item model — tracks items through stages.

Used for job application funnels, trade lifecycles, content calendars, etc.
Each Brain type defines its own stage names and transitions.
"""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import String, DateTime, Text, JSON, ForeignKey, Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class PipelineItem(Base):
    """An item tracked through pipeline stages by a Brain."""

    __tablename__ = "pipeline_items"

    item_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    brain_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("brains.brain_id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    # Pipeline definition
    pipeline_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # job_application | trade | social_post | code_review | bill_payment | custom

    # Item identity
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    external_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    external_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Stage tracking
    stage: Mapped[str] = mapped_column(String(50), nullable=False, default="discovered")
    # Generic: discovered | in_progress | action_taken | awaiting_response | completed | archived
    # Job: discovered | applied | interview_scheduled | interviewed | offer | rejected
    # Trade: signal | order_placed | filled | closed
    stage_order: Mapped[int] = mapped_column(Integer, default=0)
    stage_entered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Item data (brain-type-specific)
    data_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    # History of stage transitions
    history_json: Mapped[Optional[dict]] = mapped_column(JSON, default=list)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_starred: Mapped[bool] = mapped_column(Boolean, default=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    brain = relationship("Brain", back_populates="pipeline_items")

    def to_dict(self) -> dict:
        return {
            "item_id": self.item_id,
            "brain_id": self.brain_id,
            "pipeline_type": self.pipeline_type,
            "title": self.title,
            "external_url": self.external_url,
            "external_id": self.external_id,
            "stage": self.stage,
            "stage_order": self.stage_order,
            "stage_entered_at": self.stage_entered_at.isoformat() if self.stage_entered_at else None,
            "data": self.data_json or {},
            "history": self.history_json or [],
            "notes": self.notes,
            "is_starred": self.is_starred,
            "is_archived": self.is_archived,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
