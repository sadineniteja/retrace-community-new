"""
Brain tasks API — create, list, cancel tasks and stream execution via SSE.
"""

from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.core.security import get_current_user, CurrentUser
from app.db.database import get_session
from app.models.brain import Brain
from app.models.brain_task import BrainTask
from app.services.brain_manager import brain_manager
from app.services.task_queue import task_queue, QueuedTask

logger = structlog.get_logger()
router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────


class TaskCreate(BaseModel):
    task_type: str = Field(default="general", max_length=50)
    title: str = Field(..., min_length=1, max_length=500)
    instructions: str = Field(..., min_length=1)
    priority: int = Field(default=0, ge=0, le=10)
    requires_approval: Optional[bool] = None


class TaskResponse(BaseModel):
    task_id: str
    brain_id: str
    schedule_id: Optional[str] = None
    pipeline_item_id: Optional[str] = None
    parent_task_id: Optional[str] = None
    task_type: str
    title: str
    instructions: Optional[str] = None
    status: str
    priority: int
    trigger: str
    requires_approval: bool
    result_summary: Optional[str] = None
    error: Optional[str] = None
    cost_cents: int
    queued_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


# ── Endpoints ─────────────────────────────────────────────────────────


@router.get("/{brain_id}/tasks", response_model=list[TaskResponse])
async def list_tasks(
    brain_id: str,
    status_filter: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
):
    """List tasks for a brain, newest first."""
    brain = await brain_manager.get_brain(session, brain_id, current_user.user_id)
    if not brain:
        raise HTTPException(status_code=404, detail="Brain not found")

    q = select(BrainTask).where(BrainTask.brain_id == brain_id)
    if status_filter:
        q = q.where(BrainTask.status == status_filter)
    q = q.order_by(BrainTask.queued_at.desc()).limit(limit).offset(offset)

    result = await session.execute(q)
    tasks = result.scalars().all()
    return [TaskResponse(**t.to_dict()) for t in tasks]


@router.post("/{brain_id}/tasks", response_model=TaskResponse, status_code=201)
async def create_task(
    brain_id: str,
    data: TaskCreate,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create and enqueue a manual task for a brain."""
    brain = await brain_manager.get_brain(session, brain_id, current_user.user_id)
    if not brain:
        raise HTTPException(status_code=404, detail="Brain not found")

    if brain.status != "active":
        raise HTTPException(status_code=400, detail="Brain must be active to accept tasks")

    if brain.tasks_today >= brain.max_daily_tasks:
        raise HTTPException(status_code=429, detail="Daily task limit reached")

    requires_approval = data.requires_approval
    if requires_approval is None:
        requires_approval = brain.autonomy_level == "supervised"

    task = BrainTask(
        task_id=str(uuid4()),
        brain_id=brain_id,
        task_type=data.task_type,
        title=data.title,
        instructions=data.instructions,
        status="pending",
        priority=data.priority,
        trigger="manual",
        requires_approval=requires_approval,
    )
    session.add(task)
    await session.commit()

    # Enqueue
    await task_queue.enqueue(QueuedTask(
        task_id=task.task_id,
        brain_id=brain_id,
        user_id=current_user.user_id,
        priority=data.priority,
    ))

    return TaskResponse(**task.to_dict())


@router.get("/{brain_id}/tasks/{task_id}", response_model=TaskResponse)
async def get_task(
    brain_id: str,
    task_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get details of a specific task."""
    brain = await brain_manager.get_brain(session, brain_id, current_user.user_id)
    if not brain:
        raise HTTPException(status_code=404, detail="Brain not found")

    task = await session.get(BrainTask, task_id)
    if not task or task.brain_id != brain_id:
        raise HTTPException(status_code=404, detail="Task not found")

    return TaskResponse(**task.to_dict())


@router.post("/{brain_id}/tasks/{task_id}/cancel")
async def cancel_task(
    brain_id: str,
    task_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Cancel a pending or awaiting_approval task."""
    brain = await brain_manager.get_brain(session, brain_id, current_user.user_id)
    if not brain:
        raise HTTPException(status_code=404, detail="Brain not found")

    task = await session.get(BrainTask, task_id)
    if not task or task.brain_id != brain_id:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status not in ("pending", "awaiting_approval"):
        raise HTTPException(status_code=400, detail=f"Cannot cancel task in '{task.status}' status")

    task.status = "cancelled"
    await session.commit()
    return {"task_id": task_id, "status": "cancelled"}
