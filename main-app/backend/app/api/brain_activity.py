"""
Brain activity feed API — immutable timeline of all Brain actions.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.core.security import get_current_user, CurrentUser
from app.db.database import get_session
from app.models.brain_activity import BrainActivity
from app.services.brain_manager import brain_manager

logger = structlog.get_logger()
router = APIRouter()


class ActivityResponse(BaseModel):
    activity_id: str
    brain_id: str
    task_id: Optional[str] = None
    activity_type: str
    title: str
    description: Optional[str] = None
    detail_json: Optional[dict] = None
    severity: str
    created_at: Optional[str] = None


@router.get("/{brain_id}/activity", response_model=list[ActivityResponse])
async def list_activity(
    brain_id: str,
    severity: Optional[str] = None,
    activity_type: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get the activity feed for a brain."""
    brain = await brain_manager.get_brain(session, brain_id, current_user.user_id)
    if not brain:
        raise HTTPException(status_code=404, detail="Brain not found")

    q = select(BrainActivity).where(BrainActivity.brain_id == brain_id)
    if severity:
        q = q.where(BrainActivity.severity == severity)
    if activity_type:
        q = q.where(BrainActivity.activity_type == activity_type)
    q = q.order_by(BrainActivity.created_at.desc()).limit(limit).offset(offset)

    result = await session.execute(q)
    activities = result.scalars().all()
    return [ActivityResponse(**a.to_dict()) for a in activities]
