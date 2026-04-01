"""
Brain CRUD API — list templates, create/read/update/delete Brains, activate/pause.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.core.security import get_current_user, CurrentUser
from app.db.database import get_session
from app.services.brain_manager import brain_manager

logger = structlog.get_logger()
router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────


class BrainCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    template_slug: Optional[str] = None
    template_id: Optional[str] = None
    description: Optional[str] = None
    autonomy_level: str = Field(default="supervised", pattern="^(supervised|semi_auto|full_auto)$")


class BrainUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    autonomy_level: Optional[str] = Field(None, pattern="^(supervised|semi_auto|full_auto)$")
    max_daily_tasks: Optional[int] = Field(None, ge=1, le=1000)
    max_daily_cost_cents: Optional[int] = Field(None, ge=0, le=100000)
    config_json: Optional[dict] = None


class BrainResponse(BaseModel):
    brain_id: str
    user_id: str
    tenant_id: Optional[str] = None
    template_id: Optional[str] = None
    name: str
    brain_type: str
    description: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    setup_status: str
    setup_step: int = 0
    autonomy_level: str
    status: str
    is_active: bool
    max_daily_tasks: int
    max_daily_cost_cents: int
    tasks_today: int
    cost_today_cents: int
    config: dict = {}
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class TemplateResponse(BaseModel):
    template_id: str
    slug: str
    name: str
    description: str
    icon: str
    color: str
    category: str
    interview_questions: list
    required_accounts: list
    optional_accounts: list
    available_tools: list
    is_builtin: bool
    created_at: Optional[str] = None


# ── Templates ─────────────────────────────────────────────────────────


@router.get("/templates", response_model=list[TemplateResponse])
async def list_templates(
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
):
    """List all available brain templates."""
    templates = await brain_manager.list_templates(session)
    return [TemplateResponse(**t.to_dict()) for t in templates]


@router.get("/templates/{slug}")
async def get_template(
    slug: str,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get a specific brain template by slug."""
    template = await brain_manager.get_template_by_slug(session, slug)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return template.to_dict()


# ── Brain CRUD ────────────────────────────────────────────────────────


@router.get("", response_model=list[BrainResponse])
async def list_brains(
    status_filter: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
):
    """List all brains for the authenticated user."""
    brains = await brain_manager.list_brains(session, current_user.user_id, status_filter)
    return [BrainResponse(**b.to_dict()) for b in brains]


@router.post("", response_model=BrainResponse, status_code=status.HTTP_201_CREATED)
async def create_brain(
    data: BrainCreate,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create a new brain from a template or custom."""
    brain = await brain_manager.create_brain(
        session,
        user_id=current_user.user_id,
        name=data.name,
        template_slug=data.template_slug,
        template_id=data.template_id,
        tenant_id=current_user.tenant_id,
        description=data.description,
        autonomy_level=data.autonomy_level,
    )
    await session.commit()
    return BrainResponse(**brain.to_dict())


@router.get("/{brain_id}", response_model=BrainResponse)
async def get_brain(
    brain_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get a specific brain by ID."""
    brain = await brain_manager.get_brain(session, brain_id, current_user.user_id)
    if not brain:
        raise HTTPException(status_code=404, detail="Brain not found")
    return BrainResponse(**brain.to_dict())


@router.put("/{brain_id}", response_model=BrainResponse)
async def update_brain(
    brain_id: str,
    data: BrainUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update a brain's configuration."""
    brain = await brain_manager.get_brain(session, brain_id, current_user.user_id)
    if not brain:
        raise HTTPException(status_code=404, detail="Brain not found")

    brain = await brain_manager.update_brain(
        session, brain,
        name=data.name,
        description=data.description,
        autonomy_level=data.autonomy_level,
        max_daily_tasks=data.max_daily_tasks,
        max_daily_cost_cents=data.max_daily_cost_cents,
        config_json=data.config_json,
    )
    await session.commit()
    return BrainResponse(**brain.to_dict())


@router.delete("/{brain_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_brain(
    brain_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Delete a brain and all its associated data."""
    brain = await brain_manager.get_brain(session, brain_id, current_user.user_id)
    if not brain:
        raise HTTPException(status_code=404, detail="Brain not found")

    await brain_manager.delete_brain(session, brain)
    await session.commit()


# ── Activate / Pause ──────────────────────────────────────────────────


@router.post("/{brain_id}/activate", response_model=BrainResponse)
async def activate_brain(
    brain_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Activate a brain to start autonomous operation."""
    brain = await brain_manager.get_brain(session, brain_id, current_user.user_id)
    if not brain:
        raise HTTPException(status_code=404, detail="Brain not found")

    try:
        brain = await brain_manager.activate_brain(session, brain)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    await session.commit()
    return BrainResponse(**brain.to_dict())


@router.post("/{brain_id}/pause", response_model=BrainResponse)
async def pause_brain(
    brain_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Pause a brain's autonomous operation."""
    brain = await brain_manager.get_brain(session, brain_id, current_user.user_id)
    if not brain:
        raise HTTPException(status_code=404, detail="Brain not found")

    brain = await brain_manager.pause_brain(session, brain)
    await session.commit()
    return BrainResponse(**brain.to_dict())
