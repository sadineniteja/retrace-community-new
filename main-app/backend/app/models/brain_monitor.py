"""
Brain monitor model — watches external data and triggers alerts or tasks.

Monitors check external data sources on a schedule (stock prices, job boards,
news, websites) and trigger notifications or create tasks when conditions are met.
"""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import String, DateTime, Text, JSON, ForeignKey, Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class BrainMonitor(Base):
    """A monitor that watches external data for a Brain."""

    __tablename__ = "brain_monitors"

    monitor_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    brain_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("brains.brain_id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    monitor_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # stock_price | crypto_price | job_match | web_page | news_keyword |
    # github_repo | social_mention | rate_change | custom

    # What to watch
    target_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    target_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # e.g. {"symbol": "TSLA", "condition": "below", "value": 200}
    # or {"keywords": ["python", "remote"], "location": "Austin"}

    # How often to check
    check_interval_minutes: Mapped[int] = mapped_column(Integer, default=60)

    # What to do when triggered
    trigger_condition: Mapped[str] = mapped_column(Text, nullable=False, default="any_change")
    # any_change | keyword_match | threshold_exceeded | new_item | custom_expression
    trigger_action: Mapped[str] = mapped_column(String(50), nullable=False, default="notify")
    # notify | create_task | both
    trigger_task_instructions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notification_channels: Mapped[dict] = mapped_column(JSON, default=list)
    # e.g. ["push", "email", "sms"]

    # State
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_check_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_triggered_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    trigger_count: Mapped[int] = mapped_column(Integer, default=0)
    consecutive_errors: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    brain = relationship("Brain", back_populates="monitors")

    def to_dict(self) -> dict:
        return {
            "monitor_id": self.monitor_id,
            "brain_id": self.brain_id,
            "name": self.name,
            "monitor_type": self.monitor_type,
            "target_url": self.target_url,
            "target_config": self.target_config,
            "check_interval_minutes": self.check_interval_minutes,
            "trigger_condition": self.trigger_condition,
            "trigger_action": self.trigger_action,
            "notification_channels": self.notification_channels,
            "is_active": self.is_active,
            "last_check_at": self.last_check_at.isoformat() if self.last_check_at else None,
            "last_triggered_at": self.last_triggered_at.isoformat() if self.last_triggered_at else None,
            "trigger_count": self.trigger_count,
            "consecutive_errors": self.consecutive_errors,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
