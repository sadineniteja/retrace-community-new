"""
Brain monitors API — CRUD for monitors that watch external data and trigger actions.
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
from app.models.brain_monitor import BrainMonitor
from app.services.brain_manager import brain_manager

logger = structlog.get_logger()
router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────


class MonitorCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    monitor_type: str = Field(..., max_length=50)
    target_url: Optional[str] = None
    target_config: dict = Field(default_factory=dict)
    check_interval_minutes: int = Field(default=60, ge=1, le=1440)
    trigger_condition: str = Field(default="")
    trigger_action: str = Field(default="notify", pattern="^(notify|create_task|both)$")
    notification_channels: list[str] = Field(default_factory=lambda: ["in_app"])


class MonitorUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    target_url: Optional[str] = None
    target_config: Optional[dict] = None
    check_interval_minutes: Optional[int] = Field(None, ge=1, le=1440)
    trigger_condition: Optional[str] = None
    trigger_action: Optional[str] = Field(None, pattern="^(notify|create_task|both)$")
    notification_channels: Optional[list[str]] = None
    is_active: Optional[bool] = None


class MonitorResponse(BaseModel):
    monitor_id: str
    brain_id: str
    name: str
    monitor_type: str
    target_url: Optional[str] = None
    target_config: dict
    check_interval_minutes: int
    trigger_condition: str
    trigger_action: str
    notification_channels: list
    is_active: bool
    last_check_at: Optional[str] = None
    trigger_count: int
    created_at: Optional[str] = None


# ── Endpoints ─────────────────────────────────────────────────────────


@router.get("/{brain_id}/monitors", response_model=list[MonitorResponse])
async def list_monitors(
    brain_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
):
    brain = await brain_manager.get_brain(session, brain_id, current_user.user_id)
    if not brain:
        raise HTTPException(status_code=404, detail="Brain not found")

    result = await session.execute(
        select(BrainMonitor)
        .where(BrainMonitor.brain_id == brain_id)
        .order_by(BrainMonitor.created_at.desc())
    )
    monitors = result.scalars().all()
    return [MonitorResponse(**m.to_dict()) for m in monitors]


@router.post("/{brain_id}/monitors", response_model=MonitorResponse, status_code=201)
async def create_monitor(
    brain_id: str,
    data: MonitorCreate,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
):
    brain = await brain_manager.get_brain(session, brain_id, current_user.user_id)
    if not brain:
        raise HTTPException(status_code=404, detail="Brain not found")

    monitor = BrainMonitor(
        monitor_id=str(uuid4()),
        brain_id=brain_id,
        name=data.name,
        monitor_type=data.monitor_type,
        target_url=data.target_url,
        target_config=data.target_config,
        check_interval_minutes=data.check_interval_minutes,
        trigger_condition=data.trigger_condition,
        trigger_action=data.trigger_action,
        notification_channels=data.notification_channels,
        is_active=True,
    )
    session.add(monitor)
    await session.commit()
    return MonitorResponse(**monitor.to_dict())


@router.put("/{brain_id}/monitors/{monitor_id}", response_model=MonitorResponse)
async def update_monitor(
    brain_id: str,
    monitor_id: str,
    data: MonitorUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
):
    brain = await brain_manager.get_brain(session, brain_id, current_user.user_id)
    if not brain:
        raise HTTPException(status_code=404, detail="Brain not found")

    monitor = await session.get(BrainMonitor, monitor_id)
    if not monitor or monitor.brain_id != brain_id:
        raise HTTPException(status_code=404, detail="Monitor not found")

    for field in ("name", "target_url", "target_config", "check_interval_minutes",
                  "trigger_condition", "trigger_action", "notification_channels", "is_active"):
        val = getattr(data, field, None)
        if val is not None:
            setattr(monitor, field, val)

    await session.commit()
    return MonitorResponse(**monitor.to_dict())


@router.delete("/{brain_id}/monitors/{monitor_id}", status_code=204)
async def delete_monitor(
    brain_id: str,
    monitor_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
):
    brain = await brain_manager.get_brain(session, brain_id, current_user.user_id)
    if not brain:
        raise HTTPException(status_code=404, detail="Brain not found")

    monitor = await session.get(BrainMonitor, monitor_id)
    if not monitor or monitor.brain_id != brain_id:
        raise HTTPException(status_code=404, detail="Monitor not found")

    await session.delete(monitor)
    await session.commit()
