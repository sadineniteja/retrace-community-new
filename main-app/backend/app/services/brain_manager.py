"""
Brain lifecycle manager — create, activate, pause, configure Brains.

Handles system prompt generation from template + setup answers,
default schedule/monitor creation on activation, and daily counter resets.
"""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import structlog

from app.models.brain import Brain
from app.models.brain_template import BrainTemplate
from app.models.brain_schedule import BrainSchedule
from app.models.brain_monitor import BrainMonitor
from app.models.brain_activity import BrainActivity

logger = structlog.get_logger()


class BrainManager:
    """Service for Brain lifecycle management."""

    async def list_templates(self, session: AsyncSession) -> list[BrainTemplate]:
        result = await session.execute(
            select(BrainTemplate)
            .where(BrainTemplate.is_published == True)
            .order_by(BrainTemplate.name)
        )
        return list(result.scalars().all())

    async def get_template(self, session: AsyncSession, template_id: str) -> Optional[BrainTemplate]:
        return await session.get(BrainTemplate, template_id)

    async def get_template_by_slug(self, session: AsyncSession, slug: str) -> Optional[BrainTemplate]:
        result = await session.execute(
            select(BrainTemplate).where(BrainTemplate.slug == slug)
        )
        return result.scalar_one_or_none()

    async def list_brains(
        self, session: AsyncSession, user_id: str, status_filter: Optional[str] = None,
    ) -> list[Brain]:
        q = select(Brain).where(Brain.user_id == user_id).order_by(Brain.created_at.desc())
        if status_filter:
            q = q.where(Brain.status == status_filter)
        result = await session.execute(q)
        return list(result.scalars().all())

    async def get_brain(
        self, session: AsyncSession, brain_id: str, user_id: str,
    ) -> Optional[Brain]:
        result = await session.execute(
            select(Brain).where(Brain.brain_id == brain_id, Brain.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def create_brain(
        self,
        session: AsyncSession,
        user_id: str,
        name: str,
        template_slug: Optional[str] = None,
        template_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        description: Optional[str] = None,
        autonomy_level: str = "supervised",
    ) -> Brain:
        template: Optional[BrainTemplate] = None
        if template_slug:
            template = await self.get_template_by_slug(session, template_slug)
        elif template_id:
            template = await self.get_template(session, template_id)

        brain_type = template.slug if template else "custom"
        icon = template.icon if template else "brain"
        color = template.color if template else "#6366f1"

        brain = Brain(
            brain_id=str(uuid4()),
            user_id=user_id,
            tenant_id=tenant_id,
            template_id=template.template_id if template else None,
            name=name,
            brain_type=brain_type,
            description=description or (template.description if template else ""),
            icon=icon,
            color=color,
            setup_status="interview" if template else "ready",
            setup_step=0,
            setup_answers={},
            autonomy_level=autonomy_level,
            status="inactive",
            is_active=False,
            config_json=template.default_config if template else {},
        )

        session.add(brain)
        await session.flush()

        await self._log_activity(
            session, brain.brain_id, "brain_created",
            f"Brain '{name}' created", f"Type: {brain_type}",
        )
        return brain

    async def update_brain(
        self,
        session: AsyncSession,
        brain: Brain,
        name: Optional[str] = None,
        description: Optional[str] = None,
        autonomy_level: Optional[str] = None,
        max_daily_tasks: Optional[int] = None,
        max_daily_cost_cents: Optional[int] = None,
        config_json: Optional[dict] = None,
    ) -> Brain:
        if name is not None:
            brain.name = name
        if description is not None:
            brain.description = description
        if autonomy_level is not None:
            brain.autonomy_level = autonomy_level
        if max_daily_tasks is not None:
            brain.max_daily_tasks = max_daily_tasks
        if max_daily_cost_cents is not None:
            brain.max_daily_cost_cents = max_daily_cost_cents
        if config_json is not None:
            brain.config_json = config_json
        brain.updated_at = datetime.utcnow()
        await session.flush()
        return brain

    async def delete_brain(self, session: AsyncSession, brain: Brain) -> None:
        await self._log_activity(
            session, brain.brain_id, "brain_deleted",
            f"Brain '{brain.name}' deleted", severity="warning",
        )
        await session.delete(brain)
        await session.flush()

    async def activate_brain(self, session: AsyncSession, brain: Brain) -> Brain:
        if brain.setup_status not in ("ready",):
            raise ValueError("Brain setup must be completed before activation")

        brain.status = "active"
        brain.is_active = True
        brain.last_active_at = datetime.utcnow()
        brain.updated_at = datetime.utcnow()

        # Create default schedules from template
        if brain.template_id:
            template = await self.get_template(session, brain.template_id)
            if template and template.default_schedules:
                await self._create_default_schedules(session, brain, template.default_schedules)
            if template and template.default_monitors:
                await self._create_default_monitors(session, brain, template.default_monitors)

        await session.flush()

        await self._log_activity(
            session, brain.brain_id, "brain_activated",
            f"Brain '{brain.name}' activated",
            f"Autonomy: {brain.autonomy_level}",
        )
        return brain

    async def pause_brain(self, session: AsyncSession, brain: Brain) -> Brain:
        brain.status = "paused"
        brain.is_active = False
        brain.updated_at = datetime.utcnow()
        await session.flush()

        await self._log_activity(
            session, brain.brain_id, "brain_paused",
            f"Brain '{brain.name}' paused",
        )
        return brain

    # ── Interview ────────────────────────────────────────────────────

    async def get_interview_state(
        self, session: AsyncSession, brain: Brain,
    ) -> dict:
        template = await self.get_template(session, brain.template_id) if brain.template_id else None
        questions = template.interview_questions if template else []
        total = len(questions)
        step = brain.setup_step or 0
        current_question = questions[step] if step < total else None

        return {
            "brain_id": brain.brain_id,
            "setup_status": brain.setup_status,
            "current_step": step,
            "total_steps": total,
            "current_question": current_question,
            "answers": brain.setup_answers or {},
            "is_complete": step >= total,
        }

    async def answer_question(
        self, session: AsyncSession, brain: Brain, answer_key: str, answer_value,
    ) -> dict:
        if brain.setup_status not in ("interview", "pending"):
            raise ValueError("Brain is not in interview mode")

        template = await self.get_template(session, brain.template_id) if brain.template_id else None
        questions = template.interview_questions if template else []
        total = len(questions)

        answers = dict(brain.setup_answers or {})
        answers[answer_key] = answer_value
        brain.setup_answers = answers
        brain.setup_status = "interview"

        # Find current question index by key
        current_idx = brain.setup_step or 0
        if current_idx < total and questions[current_idx].get("key") == answer_key:
            # Advance to next question, skipping conditional questions that don't apply
            next_idx = current_idx + 1
            while next_idx < total:
                q = questions[next_idx]
                condition = q.get("condition")
                if condition:
                    cond_key = condition.get("key")
                    cond_values = condition.get("values", [])
                    cond_value = condition.get("value")
                    if cond_value:
                        cond_values = [cond_value]
                    if answers.get(cond_key) not in cond_values:
                        next_idx += 1
                        continue
                break
            brain.setup_step = next_idx

        await session.flush()
        return await self.get_interview_state(session, brain)

    async def complete_interview(self, session: AsyncSession, brain: Brain) -> Brain:
        brain.setup_status = "ready"
        brain.system_prompt = await self._generate_system_prompt(session, brain)
        brain.updated_at = datetime.utcnow()
        await session.flush()

        await self._log_activity(
            session, brain.brain_id, "setup_completed",
            f"Brain '{brain.name}' setup completed",
        )
        return brain

    async def reset_interview(self, session: AsyncSession, brain: Brain) -> Brain:
        brain.setup_status = "interview"
        brain.setup_step = 0
        brain.setup_answers = {}
        brain.system_prompt = None
        brain.updated_at = datetime.utcnow()
        await session.flush()
        return brain

    # ── Internal helpers ─────────────────────────────────────────────

    async def _generate_system_prompt(
        self, session: AsyncSession, brain: Brain,
    ) -> str:
        if not brain.template_id:
            return brain.system_prompt or "You are a helpful AI assistant."

        template = await self.get_template(session, brain.template_id)
        if not template or not template.system_prompt_template:
            return "You are a helpful AI assistant."

        prompt = template.system_prompt_template
        answers = brain.setup_answers or {}

        # Replace {setup_answers.key} placeholders
        for key, value in answers.items():
            if isinstance(value, list):
                value = ", ".join(str(v) for v in value)
            prompt = prompt.replace(f"{{setup_answers.{key}}}", str(value))

        # Replace brain identity placeholders
        prompt = prompt.replace("{brain.name}", brain.name)
        prompt = prompt.replace("{brain.autonomy_level}", brain.autonomy_level)

        return prompt

    async def _create_default_schedules(
        self, session: AsyncSession, brain: Brain, schedule_defs: list,
    ) -> None:
        for sdef in schedule_defs:
            schedule = BrainSchedule(
                schedule_id=str(uuid4()),
                brain_id=brain.brain_id,
                name=sdef.get("name", "Default Schedule"),
                task_type=sdef.get("task_type", "general"),
                task_instructions=sdef.get("task_instructions", ""),
                schedule_type=sdef.get("schedule_type", "daily"),
                schedule_config=sdef.get("schedule_config", {}),
                timezone=sdef.get("timezone", "UTC"),
                is_active=True,
            )
            session.add(schedule)

    async def _create_default_monitors(
        self, session: AsyncSession, brain: Brain, monitor_defs: list,
    ) -> None:
        for mdef in monitor_defs:
            monitor = BrainMonitor(
                monitor_id=str(uuid4()),
                brain_id=brain.brain_id,
                name=mdef.get("name", "Default Monitor"),
                monitor_type=mdef.get("monitor_type", "web_page"),
                target_url=mdef.get("target_url"),
                target_config=mdef.get("target_config", {}),
                check_interval_minutes=mdef.get("check_interval_minutes", 60),
                trigger_condition=mdef.get("trigger_condition", ""),
                trigger_action=mdef.get("trigger_action", "notify"),
                notification_channels=mdef.get("notification_channels", ["in_app"]),
                is_active=True,
            )
            session.add(monitor)

    async def _log_activity(
        self,
        session: AsyncSession,
        brain_id: str,
        activity_type: str,
        title: str,
        description: Optional[str] = None,
        severity: str = "info",
    ) -> None:
        activity = BrainActivity(
            activity_id=str(uuid4()),
            brain_id=brain_id,
            activity_type=activity_type,
            title=title,
            description=description,
            severity=severity,
        )
        session.add(activity)


brain_manager = BrainManager()
