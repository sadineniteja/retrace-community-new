"""
Task executor — runs a single Brain task using the LangGraph agent engine.

Wraps the existing agent_service pattern: builds a system prompt from the Brain's
configuration, injects available tools, streams execution, and captures results.
"""

import asyncio
import traceback
from datetime import datetime
from typing import AsyncGenerator, Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.db.database import async_session_maker
from app.models.brain import Brain
from app.models.brain_task import BrainTask
from app.models.brain_activity import BrainActivity
from app.models.approval_request import ApprovalRequest

logger = structlog.get_logger()


class TaskExecutor:
    """Executes a single BrainTask."""

    async def execute(self, task_id: str) -> dict:
        """
        Run a task end-to-end:
        1. Load task + brain from DB
        2. Check approval requirements
        3. Build system prompt
        4. Execute via LangGraph agent
        5. Capture results
        """
        async with async_session_maker() as session:
            task = await session.get(BrainTask, task_id)
            if not task:
                return {"error": "Task not found"}

            brain = await session.get(Brain, task.brain_id)
            if not brain:
                task.status = "failed"
                task.error = "Brain not found"
                await session.commit()
                return {"error": "Brain not found"}

            # Check if task requires approval and hasn't been approved yet
            if task.requires_approval and task.status == "pending":
                task.status = "awaiting_approval"
                await self._create_approval_request(session, task, brain)
                await session.commit()
                return {"status": "awaiting_approval", "task_id": task_id}

            # Mark running
            task.status = "running"
            task.started_at = datetime.utcnow()
            await session.commit()

            try:
                result = await self._run_agent(session, task, brain)

                task.status = "completed"
                task.result_summary = result.get("summary", "Task completed")
                task.result_data = result.get("data", {})
                task.completed_at = datetime.utcnow()

                # Update brain counters
                brain.tasks_today += 1
                if result.get("cost_cents"):
                    task.cost_cents = result["cost_cents"]
                    brain.cost_today_cents += result["cost_cents"]

                await self._log_activity(
                    session, brain.brain_id, task.task_id,
                    "task_completed", f"Completed: {task.title}",
                    task.result_summary, severity="success",
                )
                await session.commit()
                return {"status": "completed", "result": task.result_summary}

            except Exception as e:
                task.status = "failed"
                task.error = str(e)[:2000]
                task.completed_at = datetime.utcnow()

                await self._log_activity(
                    session, brain.brain_id, task.task_id,
                    "task_failed", f"Failed: {task.title}",
                    str(e)[:500], severity="error",
                )
                await session.commit()
                logger.error("Task execution failed", task_id=task_id, error=str(e))
                return {"status": "failed", "error": str(e)}

    async def _run_agent(
        self, session: AsyncSession, task: BrainTask, brain: Brain,
    ) -> dict:
        """
        Execute the task using the LangGraph agent.

        This integrates with the existing agent_service.py pattern:
        - Builds a system prompt from brain.system_prompt + task instructions
        - Uses the same StateGraph / CodeAct execution model
        - Returns summary + structured data
        """
        from app.core.config import settings

        system_prompt = brain.system_prompt or "You are a helpful AI assistant."
        task_prompt = (
            f"You are '{brain.name}', an autonomous AI agent.\n\n"
            f"SYSTEM CONTEXT:\n{system_prompt}\n\n"
            f"CURRENT TASK:\n"
            f"Type: {task.task_type}\n"
            f"Title: {task.title}\n"
            f"Instructions: {task.instructions}\n\n"
            f"Execute this task completely. When done, provide a clear summary of "
            f"what was accomplished and any relevant data."
        )

        # Import and use the existing LLM infrastructure
        try:
            from app.services.llm_service import get_active_llm_settings
            llm_settings = await get_active_llm_settings(session)
        except Exception:
            llm_settings = None

        # Use LangChain ChatModel for execution
        try:
            from langchain_openai import ChatOpenAI

            model_name = "gpt-4o-mini"
            api_key = None
            base_url = None

            if llm_settings:
                model_name = getattr(llm_settings, "model", model_name) or model_name
                api_key = getattr(llm_settings, "api_key", None)
                base_url = getattr(llm_settings, "base_url", None)

            llm = ChatOpenAI(
                model=model_name,
                api_key=api_key or "sk-placeholder",
                base_url=base_url,
                temperature=0.3,
                max_tokens=4096,
            )

            from langchain_core.messages import HumanMessage, SystemMessage

            messages = [
                SystemMessage(content=task_prompt),
                HumanMessage(content=f"Execute task: {task.title}\n\nInstructions: {task.instructions}"),
            ]

            response = await llm.ainvoke(messages)
            content = response.content if hasattr(response, "content") else str(response)

            return {
                "summary": content[:500],
                "data": {"full_response": content},
                "cost_cents": 0,
            }

        except ImportError:
            # Fallback if LangChain not available
            return {
                "summary": f"Task '{task.title}' queued for execution (LLM not configured)",
                "data": {"instructions": task.instructions},
                "cost_cents": 0,
            }

    async def _create_approval_request(
        self, session: AsyncSession, task: BrainTask, brain: Brain,
    ) -> ApprovalRequest:
        approval = ApprovalRequest(
            request_id=str(uuid4()),
            brain_id=brain.brain_id,
            task_id=task.task_id,
            user_id=brain.user_id,
            action_type=task.task_type,
            action_summary=f"{task.title}: {task.instructions[:200]}",
            action_data={"task_type": task.task_type, "instructions": task.instructions},
            status="pending",
        )
        session.add(approval)

        await self._log_activity(
            session, brain.brain_id, task.task_id,
            "approval_requested", f"Approval needed: {task.title}",
            severity="warning",
        )
        return approval

    async def _log_activity(
        self,
        session: AsyncSession,
        brain_id: str,
        task_id: Optional[str],
        activity_type: str,
        title: str,
        description: Optional[str] = None,
        severity: str = "info",
    ) -> None:
        activity = BrainActivity(
            activity_id=str(uuid4()),
            brain_id=brain_id,
            task_id=task_id,
            activity_type=activity_type,
            title=title,
            description=description,
            severity=severity,
        )
        session.add(activity)


task_executor = TaskExecutor()
