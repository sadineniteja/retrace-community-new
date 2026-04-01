"""
Approval queue API — list, approve, deny pending Brain action approvals.
"""

from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.core.security import get_current_user, CurrentUser
from app.db.database import get_session
from app.models.approval_request import ApprovalRequest
from app.models.brain_task import BrainTask
from app.services.task_queue import task_queue, QueuedTask

logger = structlog.get_logger()
router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────


class ApprovalResponse(BaseModel):
    request_id: str
    brain_id: str
    task_id: Optional[str] = None
    action_type: str
    action_summary: str
    action_data: Optional[dict] = None
    status: str
    expires_at: Optional[str] = None
    resolved_at: Optional[str] = None
    denial_reason: Optional[str] = None
    created_at: Optional[str] = None


class ApprovalDecision(BaseModel):
    approved: bool
    denial_reason: Optional[str] = Field(None, max_length=500)


# ── Endpoints ─────────────────────────────────────────────────────────


@router.get("", response_model=list[ApprovalResponse])
async def list_approvals(
    status_filter: str = "pending",
    brain_id: Optional[str] = None,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
):
    """List approval requests for the current user."""
    q = select(ApprovalRequest).where(ApprovalRequest.user_id == current_user.user_id)
    if status_filter:
        q = q.where(ApprovalRequest.status == status_filter)
    if brain_id:
        q = q.where(ApprovalRequest.brain_id == brain_id)
    q = q.order_by(ApprovalRequest.created_at.desc()).limit(limit)

    result = await session.execute(q)
    approvals = result.scalars().all()
    return [ApprovalResponse(**a.to_dict()) for a in approvals]


@router.get("/{request_id}", response_model=ApprovalResponse)
async def get_approval(
    request_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get a specific approval request."""
    approval = await session.get(ApprovalRequest, request_id)
    if not approval or approval.user_id != current_user.user_id:
        raise HTTPException(status_code=404, detail="Approval request not found")
    return ApprovalResponse(**approval.to_dict())


@router.post("/{request_id}/decide", response_model=ApprovalResponse)
async def decide_approval(
    request_id: str,
    data: ApprovalDecision,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Approve or deny an approval request."""
    approval = await session.get(ApprovalRequest, request_id)
    if not approval or approval.user_id != current_user.user_id:
        raise HTTPException(status_code=404, detail="Approval request not found")

    if approval.status != "pending":
        raise HTTPException(status_code=400, detail=f"Request already {approval.status}")

    # Check expiry
    if approval.expires_at and datetime.utcnow() > approval.expires_at:
        approval.status = "expired"
        await session.commit()
        raise HTTPException(status_code=400, detail="Approval request has expired")

    if data.approved:
        approval.status = "approved"
        approval.resolved_at = datetime.utcnow()

        # Resume the associated task
        if approval.task_id:
            task = await session.get(BrainTask, approval.task_id)
            if task and task.status == "awaiting_approval":
                task.status = "pending"
                task.requires_approval = False
                await session.commit()

                # Re-enqueue
                await task_queue.enqueue(QueuedTask(
                    task_id=task.task_id,
                    brain_id=task.brain_id,
                    user_id=current_user.user_id,
                    priority=task.priority,
                ))
            else:
                await session.commit()
        else:
            await session.commit()
    else:
        approval.status = "denied"
        approval.denial_reason = data.denial_reason
        approval.resolved_at = datetime.utcnow()

        # Cancel the associated task
        if approval.task_id:
            task = await session.get(BrainTask, approval.task_id)
            if task and task.status == "awaiting_approval":
                task.status = "cancelled"
                task.error = f"Denied: {data.denial_reason or 'No reason provided'}"

        await session.commit()

    return ApprovalResponse(**approval.to_dict())


@router.get("/count/pending")
async def pending_count(
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get count of pending approvals for the current user."""
    from sqlalchemy import func
    result = await session.execute(
        select(func.count(ApprovalRequest.request_id))
        .where(
            ApprovalRequest.user_id == current_user.user_id,
            ApprovalRequest.status == "pending",
        )
    )
    count = result.scalar() or 0
    return {"pending_count": count}
