"""
Brain interview API — guides users through the setup interview for a Brain.

GET  state   → current question + progress
POST answer  → submit an answer, advance to next question
POST complete → finalize interview, generate system prompt
POST reset   → restart interview from scratch
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.core.security import get_current_user, CurrentUser
from app.db.database import get_session
from app.services.brain_manager import brain_manager

logger = structlog.get_logger()
router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────


class AnswerSubmit(BaseModel):
    key: str
    value: str | int | float | bool | list | dict


class InterviewState(BaseModel):
    brain_id: str
    setup_status: str
    current_step: int
    total_steps: int
    current_question: dict | None = None
    answers: dict
    is_complete: bool


# ── Endpoints ─────────────────────────────────────────────────────────


@router.get("/{brain_id}/interview", response_model=InterviewState)
async def get_interview_state(
    brain_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get the current interview state for a brain."""
    brain = await brain_manager.get_brain(session, brain_id, current_user.user_id)
    if not brain:
        raise HTTPException(status_code=404, detail="Brain not found")

    state = await brain_manager.get_interview_state(session, brain)
    return InterviewState(**state)


@router.post("/{brain_id}/interview/answer", response_model=InterviewState)
async def submit_answer(
    brain_id: str,
    data: AnswerSubmit,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Submit an answer to the current interview question."""
    brain = await brain_manager.get_brain(session, brain_id, current_user.user_id)
    if not brain:
        raise HTTPException(status_code=404, detail="Brain not found")

    try:
        state = await brain_manager.answer_question(session, brain, data.key, data.value)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    await session.commit()
    return InterviewState(**state)


@router.post("/{brain_id}/interview/complete")
async def complete_interview(
    brain_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Complete the interview and generate the system prompt."""
    brain = await brain_manager.get_brain(session, brain_id, current_user.user_id)
    if not brain:
        raise HTTPException(status_code=404, detail="Brain not found")

    brain = await brain_manager.complete_interview(session, brain)
    await session.commit()
    return {
        "brain_id": brain.brain_id,
        "setup_status": brain.setup_status,
        "message": "Interview completed. Brain is ready to activate.",
    }


@router.post("/{brain_id}/interview/reset", response_model=InterviewState)
async def reset_interview(
    brain_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Reset the interview to start over."""
    brain = await brain_manager.get_brain(session, brain_id, current_user.user_id)
    if not brain:
        raise HTTPException(status_code=404, detail="Brain not found")

    brain = await brain_manager.reset_interview(session, brain)
    await session.commit()

    state = await brain_manager.get_interview_state(session, brain)
    return InterviewState(**state)
