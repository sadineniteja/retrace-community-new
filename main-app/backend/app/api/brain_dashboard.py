"""
Brain dashboard API — aggregated stats and overview for Brain management.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.core.security import get_current_user, CurrentUser
from app.db.database import get_session
from app.models.brain import Brain
from app.models.brain_task import BrainTask
from app.models.brain_activity import BrainActivity
from app.models.brain_monitor import BrainMonitor
from app.models.pipeline_item import PipelineItem
from app.models.connected_account import ConnectedAccount
from app.models.approval_request import ApprovalRequest

logger = structlog.get_logger()
router = APIRouter()


@router.get("/overview")
async def dashboard_overview(
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get a high-level overview of all user's brains."""
    # Brain counts by status
    brain_result = await session.execute(
        select(Brain.status, func.count(Brain.brain_id))
        .where(Brain.user_id == current_user.user_id)
        .group_by(Brain.status)
    )
    brain_counts = dict(brain_result.all())

    # Total tasks today
    total_tasks_today = await session.execute(
        select(func.sum(Brain.tasks_today))
        .where(Brain.user_id == current_user.user_id)
    )
    tasks_today = total_tasks_today.scalar() or 0

    # Total cost today
    total_cost = await session.execute(
        select(func.sum(Brain.cost_today_cents))
        .where(Brain.user_id == current_user.user_id)
    )
    cost_today = total_cost.scalar() or 0

    # Pending approvals
    pending_approvals = await session.execute(
        select(func.count(ApprovalRequest.request_id))
        .where(
            ApprovalRequest.user_id == current_user.user_id,
            ApprovalRequest.status == "pending",
        )
    )
    pending_count = pending_approvals.scalar() or 0

    return {
        "brains": {
            "total": sum(brain_counts.values()),
            "active": brain_counts.get("active", 0),
            "paused": brain_counts.get("paused", 0),
            "inactive": brain_counts.get("inactive", 0),
        },
        "today": {
            "tasks_completed": tasks_today,
            "cost_cents": cost_today,
        },
        "pending_approvals": pending_count,
    }


@router.get("/{brain_id}/stats")
async def brain_stats(
    brain_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get detailed stats for a specific brain."""
    from app.services.brain_manager import brain_manager

    brain = await brain_manager.get_brain(session, brain_id, current_user.user_id)
    if not brain:
        raise HTTPException(status_code=404, detail="Brain not found")

    # Task counts by status
    task_result = await session.execute(
        select(BrainTask.status, func.count(BrainTask.task_id))
        .where(BrainTask.brain_id == brain_id)
        .group_by(BrainTask.status)
    )
    task_counts = dict(task_result.all())

    # Pipeline counts by stage
    pipeline_result = await session.execute(
        select(PipelineItem.stage, func.count(PipelineItem.item_id))
        .where(PipelineItem.brain_id == brain_id, PipelineItem.is_archived == False)
        .group_by(PipelineItem.stage)
    )
    pipeline_counts = dict(pipeline_result.all())

    # Connected accounts
    accounts_count = await session.execute(
        select(func.count(ConnectedAccount.account_id))
        .where(ConnectedAccount.brain_id == brain_id)
    )

    # Active monitors
    monitors_count = await session.execute(
        select(func.count(BrainMonitor.monitor_id))
        .where(BrainMonitor.brain_id == brain_id, BrainMonitor.is_active == True)
    )

    # Recent activity count
    activity_count = await session.execute(
        select(func.count(BrainActivity.activity_id))
        .where(BrainActivity.brain_id == brain_id)
    )

    return {
        "brain": brain.to_dict(),
        "tasks": {
            "total": sum(task_counts.values()),
            "by_status": task_counts,
        },
        "pipeline": {
            "total": sum(pipeline_counts.values()),
            "by_stage": pipeline_counts,
        },
        "connected_accounts": accounts_count.scalar() or 0,
        "active_monitors": monitors_count.scalar() or 0,
        "total_activities": activity_count.scalar() or 0,
    }
