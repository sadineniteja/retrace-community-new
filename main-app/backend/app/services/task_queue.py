"""
In-memory task queue for Brain tasks.

Tasks are queued here and picked up by the task worker for execution.
In production, swap this for Redis-backed queue (see redis_queue.py plan).
"""

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import structlog

logger = structlog.get_logger()


@dataclass
class QueuedTask:
    task_id: str
    brain_id: str
    user_id: str
    priority: int = 0  # higher = more urgent
    queued_at: datetime = field(default_factory=datetime.utcnow)


class TaskQueue:
    """Priority-based in-memory task queue."""

    def __init__(self):
        self._queue: asyncio.PriorityQueue[tuple[int, float, QueuedTask]] = asyncio.PriorityQueue()
        self._active: dict[str, QueuedTask] = {}  # task_id → QueuedTask
        self._brain_active_count: dict[str, int] = defaultdict(int)

    async def enqueue(self, task: QueuedTask) -> None:
        # Priority queue: lower number = higher priority; negate so higher priority runs first
        await self._queue.put((-task.priority, task.queued_at.timestamp(), task))
        logger.info("Task queued", task_id=task.task_id, brain_id=task.brain_id)

    async def dequeue(self, max_per_brain: int = 3) -> Optional[QueuedTask]:
        """Get next task, respecting per-brain concurrency limits."""
        skipped: list[tuple[int, float, QueuedTask]] = []
        result: Optional[QueuedTask] = None

        while not self._queue.empty():
            item = await self._queue.get()
            _, _, task = item

            if self._brain_active_count[task.brain_id] >= max_per_brain:
                skipped.append(item)
                continue

            result = task
            self._active[task.task_id] = task
            self._brain_active_count[task.brain_id] += 1
            break

        # Put skipped items back
        for item in skipped:
            await self._queue.put(item)

        return result

    def mark_complete(self, task_id: str) -> None:
        task = self._active.pop(task_id, None)
        if task:
            self._brain_active_count[task.brain_id] = max(
                0, self._brain_active_count[task.brain_id] - 1
            )

    @property
    def pending_count(self) -> int:
        return self._queue.qsize()

    @property
    def active_count(self) -> int:
        return len(self._active)

    def is_task_active(self, task_id: str) -> bool:
        return task_id in self._active

    def get_brain_active_count(self, brain_id: str) -> int:
        return self._brain_active_count.get(brain_id, 0)


task_queue = TaskQueue()
