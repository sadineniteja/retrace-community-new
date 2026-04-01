"""
Approval request model — human-in-the-loop approval for Brain actions.

When a Brain's autonomy level requires approval for certain actions,
an ApprovalRequest is created and the task waits until the user approves or denies.
"""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import String, DateTime, Text, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class ApprovalRequest(Base):
    """A request for human approval of a Brain action."""

    __tablename__ = "approval_requests"

    request_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    brain_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("brains.brain_id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("brain_tasks.task_id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.user_id"), nullable=False, index=True,
    )

    # What action needs approval
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # send_message | submit_application | execute_trade | publish_post |
    # make_payment | delete_data | connect_account | custom
    action_summary: Mapped[str] = mapped_column(String(500), nullable=False)
    action_detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    action_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Status
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )  # pending | approved | denied | expired | auto_approved

    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    resolved_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    denial_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "brain_id": self.brain_id,
            "task_id": self.task_id,
            "user_id": self.user_id,
            "action_type": self.action_type,
            "action_summary": self.action_summary,
            "action_detail": self.action_detail,
            "action_data": self.action_data,
            "status": self.status,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "resolved_by": self.resolved_by,
            "denial_reason": self.denial_reason,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
