"""
Monitor service — periodic checks on external data sources that trigger alerts/tasks.

Monitors run on an interval (configurable per-monitor), check a condition,
and either notify the user, create a task, or both.
"""

import asyncio
import json
from datetime import datetime
from typing import Optional
from uuid import uuid4

import httpx
import structlog

from app.db.database import async_session_maker
from app.models.brain import Brain
from app.models.brain_monitor import BrainMonitor
from app.models.brain_task import BrainTask
from app.models.brain_activity import BrainActivity
from app.services.task_queue import task_queue, QueuedTask

logger = structlog.get_logger()


class MonitorService:
    """Runs periodic monitor checks and triggers actions."""

    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._check_loop())
        logger.info("Monitor service started")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Monitor service stopped")

    async def _check_loop(self) -> None:
        """Main loop: every 60s, find monitors due for check and run them."""
        while self._running:
            try:
                await self._run_due_checks()
            except Exception as e:
                logger.error("Monitor check loop error", error=str(e))
            await asyncio.sleep(60)

    async def _run_due_checks(self) -> None:
        from sqlalchemy import select

        async with async_session_maker() as session:
            now = datetime.utcnow()

            result = await session.execute(
                select(BrainMonitor)
                .join(Brain, BrainMonitor.brain_id == Brain.brain_id)
                .where(BrainMonitor.is_active == True, Brain.status == "active")
            )
            monitors = result.scalars().all()

            for monitor in monitors:
                # Check if due
                if monitor.last_check_at:
                    elapsed = (now - monitor.last_check_at).total_seconds() / 60
                    if elapsed < monitor.check_interval_minutes:
                        continue

                try:
                    triggered = await self._check_monitor(session, monitor)
                    monitor.last_check_at = now
                    if triggered:
                        monitor.trigger_count = (monitor.trigger_count or 0) + 1
                    await session.commit()
                except Exception as e:
                    logger.error(
                        "Monitor check failed",
                        monitor_id=monitor.monitor_id, error=str(e),
                    )
                    await session.rollback()

    async def _check_monitor(
        self, session, monitor: BrainMonitor,
    ) -> bool:
        """Run a single monitor check. Returns True if triggered."""
        snapshot = await self._fetch_snapshot(monitor)
        if snapshot is None:
            return False

        previous = monitor.last_snapshot
        monitor.last_snapshot = snapshot

        triggered = self._evaluate_trigger(monitor, snapshot, previous)
        if not triggered:
            return False

        # Execute trigger action
        brain = await session.get(Brain, monitor.brain_id)
        if not brain:
            return False

        if monitor.trigger_action in ("notify", "both"):
            await self._send_notification(session, monitor, brain, snapshot)

        if monitor.trigger_action in ("create_task", "both"):
            await self._create_triggered_task(session, monitor, brain, snapshot)

        return True

    async def _fetch_snapshot(self, monitor: BrainMonitor) -> Optional[dict]:
        """Fetch current data from the monitor's target."""
        config = monitor.target_config or {}

        if monitor.monitor_type in ("web_page", "news_keyword"):
            url = monitor.target_url or config.get("url")
            if not url:
                return None
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.get(url)
                    return {
                        "status_code": resp.status_code,
                        "content_length": len(resp.text),
                        "snippet": resp.text[:1000],
                        "checked_at": datetime.utcnow().isoformat(),
                    }
            except Exception as e:
                return {"error": str(e), "checked_at": datetime.utcnow().isoformat()}

        elif monitor.monitor_type in ("stock_price", "crypto_price"):
            # Placeholder for price API integration
            symbol = config.get("symbol", "")
            return {
                "symbol": symbol,
                "price": None,  # Would be fetched from a price API
                "checked_at": datetime.utcnow().isoformat(),
            }

        elif monitor.monitor_type == "api_endpoint":
            url = monitor.target_url or config.get("url")
            headers = config.get("headers", {})
            if not url:
                return None
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.get(url, headers=headers)
                    return {
                        "status_code": resp.status_code,
                        "data": resp.json() if "json" in resp.headers.get("content-type", "") else resp.text[:1000],
                        "checked_at": datetime.utcnow().isoformat(),
                    }
            except Exception as e:
                return {"error": str(e)}

        return None

    def _evaluate_trigger(
        self, monitor: BrainMonitor, current: dict, previous: Optional[dict],
    ) -> bool:
        """Evaluate whether the trigger condition is met."""
        condition = monitor.trigger_condition or ""

        if not condition:
            # No condition = trigger on any change
            return previous is not None and current != previous

        # Simple condition evaluators
        if condition == "content_changed":
            if not previous:
                return False
            return current.get("snippet") != previous.get("snippet")

        if condition == "status_error":
            return current.get("status_code", 200) >= 400

        if condition.startswith("price_above:"):
            try:
                threshold = float(condition.split(":")[1])
                price = current.get("price")
                return price is not None and price > threshold
            except (ValueError, IndexError):
                return False

        if condition.startswith("price_below:"):
            try:
                threshold = float(condition.split(":")[1])
                price = current.get("price")
                return price is not None and price < threshold
            except (ValueError, IndexError):
                return False

        if condition.startswith("keyword:"):
            keyword = condition.split(":", 1)[1].strip().lower()
            snippet = (current.get("snippet") or "").lower()
            return keyword in snippet

        return False

    async def _send_notification(
        self, session, monitor: BrainMonitor, brain: Brain, snapshot: dict,
    ) -> None:
        activity = BrainActivity(
            activity_id=str(uuid4()),
            brain_id=brain.brain_id,
            activity_type="monitor_triggered",
            title=f"Monitor alert: {monitor.name}",
            description=f"Condition '{monitor.trigger_condition}' triggered",
            detail_json={"monitor_id": monitor.monitor_id, "snapshot": snapshot},
            severity="warning",
        )
        session.add(activity)

    async def _create_triggered_task(
        self, session, monitor: BrainMonitor, brain: Brain, snapshot: dict,
    ) -> None:
        task = BrainTask(
            task_id=str(uuid4()),
            brain_id=brain.brain_id,
            task_type=f"monitor_{monitor.monitor_type}",
            title=f"Monitor triggered: {monitor.name}",
            instructions=(
                f"The monitor '{monitor.name}' (type: {monitor.monitor_type}) "
                f"detected a trigger condition: {monitor.trigger_condition}.\n"
                f"Current snapshot: {json.dumps(snapshot, default=str)[:1000]}\n"
                f"Take appropriate action based on the brain's configuration."
            ),
            status="pending",
            trigger="monitor",
            requires_approval=(brain.autonomy_level == "supervised"),
        )
        session.add(task)
        await session.flush()

        await task_queue.enqueue(QueuedTask(
            task_id=task.task_id,
            brain_id=brain.brain_id,
            user_id=brain.user_id,
        ))


monitor_service = MonitorService()
