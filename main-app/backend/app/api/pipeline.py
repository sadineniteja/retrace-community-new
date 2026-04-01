"""
Pipeline API — Kanban-style tracking for Brain work items.

Items move through stages: discovered → applied → interview → offer (job search),
or: idea → drafted → scheduled → posted → analyzing (social media), etc.
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
from app.models.pipeline_item import PipelineItem
from app.services.brain_manager import brain_manager

logger = structlog.get_logger()
router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────


class PipelineItemCreate(BaseModel):
    pipeline_type: str = Field(..., max_length=50)
    title: str = Field(..., min_length=1, max_length=500)
    external_url: Optional[str] = None
    stage: str = Field(default="new", max_length=50)
    stage_order: int = Field(default=0)
    data_json: dict = Field(default_factory=dict)


class PipelineItemUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    stage: Optional[str] = Field(None, max_length=50)
    stage_order: Optional[int] = None
    external_url: Optional[str] = None
    data_json: Optional[dict] = None
    is_starred: Optional[bool] = None
    is_archived: Optional[bool] = None


class PipelineItemResponse(BaseModel):
    item_id: str
    brain_id: str
    pipeline_type: str
    title: str
    external_url: Optional[str] = None
    stage: str
    stage_order: int
    data_json: dict
    history_json: list
    is_starred: bool
    is_archived: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# ── Endpoints ─────────────────────────────────────────────────────────


@router.get("/{brain_id}/pipeline", response_model=list[PipelineItemResponse])
async def list_pipeline_items(
    brain_id: str,
    pipeline_type: Optional[str] = None,
    stage: Optional[str] = None,
    is_archived: bool = False,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
):
    brain = await brain_manager.get_brain(session, brain_id, current_user.user_id)
    if not brain:
        raise HTTPException(status_code=404, detail="Brain not found")

    q = select(PipelineItem).where(
        PipelineItem.brain_id == brain_id,
        PipelineItem.is_archived == is_archived,
    )
    if pipeline_type:
        q = q.where(PipelineItem.pipeline_type == pipeline_type)
    if stage:
        q = q.where(PipelineItem.stage == stage)
    q = q.order_by(PipelineItem.stage_order, PipelineItem.created_at.desc())

    result = await session.execute(q)
    items = result.scalars().all()
    return [PipelineItemResponse(**i.to_dict()) for i in items]


@router.post("/{brain_id}/pipeline", response_model=PipelineItemResponse, status_code=201)
async def create_pipeline_item(
    brain_id: str,
    data: PipelineItemCreate,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
):
    brain = await brain_manager.get_brain(session, brain_id, current_user.user_id)
    if not brain:
        raise HTTPException(status_code=404, detail="Brain not found")

    item = PipelineItem(
        item_id=str(uuid4()),
        brain_id=brain_id,
        pipeline_type=data.pipeline_type,
        title=data.title,
        external_url=data.external_url,
        stage=data.stage,
        stage_order=data.stage_order,
        data_json=data.data_json,
        history_json=[{"stage": data.stage, "timestamp": __import__("datetime").datetime.utcnow().isoformat()}],
    )
    session.add(item)
    await session.commit()
    return PipelineItemResponse(**item.to_dict())


@router.put("/{brain_id}/pipeline/{item_id}", response_model=PipelineItemResponse)
async def update_pipeline_item(
    brain_id: str,
    item_id: str,
    data: PipelineItemUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
):
    brain = await brain_manager.get_brain(session, brain_id, current_user.user_id)
    if not brain:
        raise HTTPException(status_code=404, detail="Brain not found")

    item = await session.get(PipelineItem, item_id)
    if not item or item.brain_id != brain_id:
        raise HTTPException(status_code=404, detail="Pipeline item not found")

    # Track stage changes in history
    if data.stage and data.stage != item.stage:
        history = list(item.history_json or [])
        history.append({
            "stage": data.stage,
            "from_stage": item.stage,
            "timestamp": __import__("datetime").datetime.utcnow().isoformat(),
        })
        item.history_json = history

    for field in ("title", "stage", "stage_order", "external_url", "data_json", "is_starred", "is_archived"):
        val = getattr(data, field, None)
        if val is not None:
            setattr(item, field, val)

    await session.commit()
    return PipelineItemResponse(**item.to_dict())


@router.delete("/{brain_id}/pipeline/{item_id}", status_code=204)
async def delete_pipeline_item(
    brain_id: str,
    item_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
):
    brain = await brain_manager.get_brain(session, brain_id, current_user.user_id)
    if not brain:
        raise HTTPException(status_code=404, detail="Brain not found")

    item = await session.get(PipelineItem, item_id)
    if not item or item.brain_id != brain_id:
        raise HTTPException(status_code=404, detail="Pipeline item not found")

    await session.delete(item)
    await session.commit()
