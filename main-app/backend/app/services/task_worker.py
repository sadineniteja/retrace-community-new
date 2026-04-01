"""
Background task worker — continuously dequeues and executes Brain tasks.

Started as an asyncio background task during app lifespan.
Respects per-brain concurrency limits and global max concurrent tasks.
"""

import asyncio
from datetime import datetime

import structlog

from app.core.config import settings
from app.services.task_queue import task_queue
from app.services.task_executor import task_executor

logger = structlog.get_logger()


class TaskWorker:
    """Background worker that processes queued Brain tasks."""

    def __init__(self):
        self._running = False
        self._task: asyncio.Task | None = None
        self._semaphore: asyncio.Semaphore | None = None

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._semaphore = asyncio.Semaphore(settings.BRAIN_MAX_CONCURRENT_TASKS)
        self._task = asyncio.create_task(self._worker_loop())
        logger.info("Task worker started", max_concurrent=settings.BRAIN_MAX_CONCURRENT_TASKS)

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Task worker stopped")

    async def _worker_loop(self) -> None:
        while self._running:
            try:
                task = await task_queue.dequeue()
                if task is None:
                    await asyncio.sleep(1)
                    continue

                # Run with concurrency limit
                await self._semaphore.acquire()
                asyncio.create_task(self._execute_with_cleanup(task))

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Worker loop error", error=str(e))
                await asyncio.sleep(5)

    async def _execute_with_cleanup(self, queued_task) -> None:
        try:
            await asyncio.wait_for(
                task_executor.execute(queued_task.task_id),
                timeout=settings.BRAIN_TASK_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.error("Task timed out", task_id=queued_task.task_id)
            # Mark task as failed in DB
            from app.db.database import async_session_maker
            from app.models.brain_task import BrainTask
            async with async_session_maker() as session:
                task = await session.get(BrainTask, queued_task.task_id)
                if task:
                    task.status = "failed"
                    task.error = f"Task timed out after {settings.BRAIN_TASK_TIMEOUT_SECONDS}s"
                    task.completed_at = datetime.utcnow()
                    await session.commit()
        except Exception as e:
            logger.error("Task execution error", task_id=queued_task.task_id, error=str(e))
        finally:
            task_queue.mark_complete(queued_task.task_id)
            self._semaphore.release()


task_worker = TaskWorker()
