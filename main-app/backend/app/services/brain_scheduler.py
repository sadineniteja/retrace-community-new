"""
Brain scheduler — manages recurring schedules for Brain tasks.

Extends the existing APScheduler pattern from scheduler_service.py
to create BrainTask records on each scheduled trigger.
"""

import asyncio
from datetime import datetime
from typing import Optional
from uuid import uuid4

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
import structlog

from app.db.database import async_session_maker
from app.models.brain import Brain
from app.models.brain_schedule import BrainSchedule
from app.models.brain_task import BrainTask
from app.services.task_queue import task_queue, QueuedTask

logger = structlog.get_logger()


class BrainScheduler:
    """Manages APScheduler jobs for Brain schedules."""

    def __init__(self):
        self._scheduler: Optional[AsyncIOScheduler] = None

    async def start(self) -> None:
        self._scheduler = AsyncIOScheduler(
            job_defaults={"misfire_grace_time": 300, "coalesce": True}
        )
        self._scheduler.start()
        await self._load_active_schedules()
        logger.info("Brain scheduler started")

    async def stop(self) -> None:
        if self._scheduler:
            self._scheduler.shutdown(wait=False)
            logger.info("Brain scheduler stopped")

    async def _load_active_schedules(self) -> None:
        """Load all active schedules from DB and register APScheduler jobs."""
        from sqlalchemy import select

        async with async_session_maker() as session:
            result = await session.execute(
                select(BrainSchedule)
                .join(Brain, BrainSchedule.brain_id == Brain.brain_id)
                .where(BrainSchedule.is_active == True, Brain.status == "active")
            )
            schedules = result.scalars().all()

            for schedule in schedules:
                self._add_job(schedule)

            logger.info("Loaded brain schedules", count=len(schedules))

    def add_schedule(self, schedule: BrainSchedule) -> None:
        self._add_job(schedule)

    def remove_schedule(self, schedule_id: str) -> None:
        job_id = f"brain_schedule_{schedule_id}"
        if self._scheduler and self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)

    def _add_job(self, schedule: BrainSchedule) -> None:
        if not self._scheduler:
            return

        job_id = f"brain_schedule_{schedule.schedule_id}"
        trigger = self._build_trigger(schedule)
        if not trigger:
            logger.warning("Could not build trigger", schedule_id=schedule.schedule_id)
            return

        self._scheduler.add_job(
            _execute_scheduled_task,
            trigger=trigger,
            id=job_id,
            args=[schedule.schedule_id, schedule.brain_id],
            replace_existing=True,
        )

    def _build_trigger(self, schedule: BrainSchedule):
        config = schedule.schedule_config or {}
        tz = schedule.timezone or "UTC"

        if schedule.schedule_type == "once":
            run_at = config.get("run_at")
            if run_at:
                return DateTrigger(run_date=run_at, timezone=tz)

        elif schedule.schedule_type == "interval":
            return IntervalTrigger(
                minutes=config.get("minutes", 0),
                hours=config.get("hours", 0),
                days=config.get("days", 0),
                timezone=tz,
            )

        elif schedule.schedule_type == "daily":
            hour = config.get("hour", 9)
            minute = config.get("minute", 0)
            return CronTrigger(hour=hour, minute=minute, timezone=tz)

        elif schedule.schedule_type == "weekly":
            days = config.get("days_of_week", "mon")
            hour = config.get("hour", 9)
            minute = config.get("minute", 0)
            return CronTrigger(
                day_of_week=days, hour=hour, minute=minute, timezone=tz,
            )

        elif schedule.schedule_type == "monthly":
            day = config.get("day", 1)
            hour = config.get("hour", 9)
            minute = config.get("minute", 0)
            return CronTrigger(day=day, hour=hour, minute=minute, timezone=tz)

        elif schedule.schedule_type == "cron":
            expr = config.get("expression", "0 9 * * *")
            parts = expr.split()
            if len(parts) == 5:
                return CronTrigger(
                    minute=parts[0], hour=parts[1], day=parts[2],
                    month=parts[3], day_of_week=parts[4], timezone=tz,
                )

        return None


async def _execute_scheduled_task(schedule_id: str, brain_id: str) -> None:
    """APScheduler callback: create a BrainTask and enqueue it."""
    async with async_session_maker() as session:
        schedule = await session.get(BrainSchedule, schedule_id)
        if not schedule or not schedule.is_active:
            return

        brain = await session.get(Brain, brain_id)
        if not brain or brain.status != "active":
            return

        # Check daily limits
        if brain.tasks_today >= brain.max_daily_tasks:
            logger.warning("Brain daily task limit reached", brain_id=brain_id)
            return

        task = BrainTask(
            task_id=str(uuid4()),
            brain_id=brain_id,
            schedule_id=schedule_id,
            task_type=schedule.task_type,
            title=f"Scheduled: {schedule.name}",
            instructions=schedule.task_instructions,
            status="pending",
            trigger="scheduled",
            requires_approval=(brain.autonomy_level == "supervised"),
        )
        session.add(task)

        schedule.last_run_at = datetime.utcnow()
        await session.commit()

        # Enqueue for execution
        await task_queue.enqueue(QueuedTask(
            task_id=task.task_id,
            brain_id=brain_id,
            user_id=brain.user_id,
        ))

        logger.info("Scheduled task created", task_id=task.task_id, schedule=schedule.name)


brain_scheduler = BrainScheduler()
