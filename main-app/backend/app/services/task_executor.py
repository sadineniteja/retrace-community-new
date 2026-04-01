"""
Task executor — runs a single Brain task using browser automation + LLM.

For browser-based tasks (job_search, apply, monitor):
  1. Loads brain's connected account cookies
  2. Opens a BrainBrowserSession (streamed live to user)
  3. Executes the task using brain-specific tools
  4. Captures results + screenshots

For LLM-only tasks:
  Uses LangChain ChatOpenAI to generate text responses.
"""

import asyncio
import json
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.db.database import async_session_maker
from app.models.brain import Brain
from app.models.brain_task import BrainTask
from app.models.brain_activity import BrainActivity
from app.models.approval_request import ApprovalRequest
from app.models.connected_account import ConnectedAccount
from app.models.pipeline_item import PipelineItem

logger = structlog.get_logger()


class TaskExecutor:
    """Executes a single BrainTask."""

    async def execute(self, task_id: str) -> dict:
        """
        Run a task end-to-end:
        1. Load task + brain from DB
        2. Check approval requirements
        3. Route to browser or LLM executor
        4. Capture results
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
                # Route based on task type
                if task.task_type in (
                    "job_search", "job_apply", "linkedin_search",
                    "linkedin_apply", "browser_task", "web_monitor",
                ):
                    result = await self._run_browser_task(session, task, brain)
                else:
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

    async def _run_browser_task(
        self, session: AsyncSession, task: BrainTask, brain: Brain,
    ) -> dict:
        """
        Execute a browser-based task (LinkedIn job search, apply, etc.).
        Opens a live-streamed browser session.
        """
        from app.services.brain_browser_manager import brain_browser_manager
        from app.services.credential_manager import credential_manager

        await self._log_activity(
            session, brain.brain_id, task.task_id,
            "browser_started", f"Starting browser for: {task.title}",
            severity="info",
        )
        await session.commit()

        # Load LinkedIn cookies if available
        cookies = []
        user_agent = None
        result = await session.execute(
            select(ConnectedAccount).where(
                ConnectedAccount.brain_id == brain.brain_id,
                ConnectedAccount.provider.in_(["linkedin", "LinkedIn"]),
                ConnectedAccount.status == "active",
            )
        )
        linkedin_account = result.scalar_one_or_none()
        if linkedin_account and linkedin_account.credentials_encrypted:
            creds = credential_manager.decrypt_credentials(linkedin_account.credentials_encrypted)
            cookies = creds.get("cookies", [])
            user_agent = creds.get("user_agent")

        # Create browser session
        browser_session = await brain_browser_manager.get_or_create(
            brain_id=brain.brain_id,
            task_id=task.task_id,
            cookies=cookies if cookies else None,
            user_agent=user_agent,
        )

        page = browser_session.page

        try:
            # Parse task instructions for parameters
            instructions = task.instructions or ""
            config = brain.config_json or {}

            if task.task_type in ("job_search", "linkedin_search"):
                return await self._execute_job_search(
                    session, page, browser_session, brain, task, config, instructions,
                )
            elif task.task_type in ("job_apply", "linkedin_apply"):
                return await self._execute_job_apply(
                    session, page, browser_session, brain, task, config, instructions,
                )
            elif task.task_type == "browser_task":
                return await self._execute_generic_browser(
                    page, browser_session, task, instructions,
                )
            else:
                return await self._execute_generic_browser(
                    page, browser_session, task, instructions,
                )

        finally:
            # Don't close the session immediately — keep it alive for user to view
            browser_session.is_running = False
            await browser_session.broadcast_status("Task completed — browser session remains active")

    async def _execute_job_search(
        self,
        session: AsyncSession,
        page,
        browser_session,
        brain: Brain,
        task: BrainTask,
        config: dict,
        instructions: str,
    ) -> dict:
        """Run a LinkedIn job search and populate the pipeline."""
        from app.tools.brain_tools.job_search import (
            verify_linkedin_login,
            linkedin_search_jobs,
        )

        await browser_session.broadcast_status("Verifying LinkedIn login...")

        # Verify login (with blockage detection)
        login_status = await verify_linkedin_login(page, browser_session=browser_session)
        if not login_status.get("logged_in"):
            await self._log_activity(
                session, brain.brain_id, task.task_id,
                "linkedin_login_failed", "LinkedIn session expired",
                login_status.get("reason", "Unknown"), severity="error",
            )
            return {
                "summary": f"LinkedIn login failed: {login_status.get('reason')}",
                "data": login_status,
            }

        await browser_session.broadcast_status("Searching for jobs...")

        # Extract search parameters from brain config and task instructions
        keywords = config.get("job_titles", ["Software Engineer"])
        if isinstance(keywords, list):
            keywords = ", ".join(keywords)
        location = config.get("preferred_locations", [""])[0] if isinstance(config.get("preferred_locations"), list) else ""

        filters = {}
        if config.get("job_type"):
            filters["job_type"] = config["job_type"]
        if config.get("remote_preference"):
            filters["remote"] = config["remote_preference"]
        filters["easy_apply"] = True  # Prefer Easy Apply

        # Search (with blockage detection)
        jobs = await linkedin_search_jobs(
            page,
            keywords=keywords,
            location=location,
            filters=filters,
            max_results=15,
            browser_session=browser_session,
        )

        await browser_session.broadcast_status(f"Found {len(jobs)} jobs. Saving to pipeline...")

        # Add jobs to pipeline
        new_count = 0
        for job in jobs:
            # Check if already in pipeline
            existing = await session.execute(
                select(PipelineItem).where(
                    PipelineItem.brain_id == brain.brain_id,
                    PipelineItem.external_url == job.get("url"),
                )
            )
            if existing.scalar_one_or_none():
                continue

            pipeline_item = PipelineItem(
                item_id=str(uuid4()),
                brain_id=brain.brain_id,
                pipeline_type="job_application",
                title=f"{job.get('title', 'Unknown')} at {job.get('company', 'Unknown')}",
                external_url=job.get("url", ""),
                stage="discovered",
                stage_order=0,
                data_json={
                    "company": job.get("company"),
                    "location": job.get("location"),
                    "posted_date": job.get("posted_date"),
                    "job_id": job.get("job_id"),
                },
                history_json=[{"stage": "discovered", "timestamp": datetime.utcnow().isoformat()}],
            )
            session.add(pipeline_item)
            new_count += 1

        await session.flush()

        summary = f"Found {len(jobs)} jobs, added {new_count} new to pipeline. Keywords: {keywords}"
        return {
            "summary": summary,
            "data": {"jobs_found": len(jobs), "new_added": new_count, "jobs": jobs[:5]},
        }

    async def _execute_job_apply(
        self,
        session: AsyncSession,
        page,
        browser_session,
        brain: Brain,
        task: BrainTask,
        config: dict,
        instructions: str,
    ) -> dict:
        """Apply to a specific job via LinkedIn Easy Apply."""
        from app.tools.brain_tools.job_search import (
            verify_linkedin_login,
            linkedin_apply_easy,
        )

        # Verify login (with blockage detection)
        login_status = await verify_linkedin_login(page, browser_session=browser_session)
        if not login_status.get("logged_in"):
            return {"summary": f"LinkedIn login failed: {login_status.get('reason')}", "data": login_status}

        # Get job URL from instructions or task data
        job_url = ""
        if "linkedin.com/jobs" in instructions:
            import re
            urls = re.findall(r'https?://\S*linkedin\.com/jobs/view/\S*', instructions)
            if urls:
                job_url = urls[0]

        if not job_url:
            return {"summary": "No job URL provided in instructions", "data": {}}

        await browser_session.broadcast_status(f"Applying to job...")

        # Find resume path
        resume_path = None
        upload_dir = Path(__file__).parent.parent / "uploads" / "brain_files" / brain.brain_id
        if upload_dir.exists():
            for f in upload_dir.iterdir():
                if f.suffix.lower() in (".pdf", ".doc", ".docx"):
                    resume_path = str(f)
                    break

        # Build answers from brain config
        answers = {}
        if config.get("email"):
            answers["email"] = config["email"]
        if config.get("phone"):
            answers["phone"] = config["phone"]
        if config.get("years_experience"):
            answers["years_experience"] = str(config["years_experience"])

        result = await linkedin_apply_easy(
            page,
            job_url=job_url,
            resume_path=resume_path,
            answers=answers,
            browser_session=browser_session,
        )

        # Update pipeline item stage if application was submitted
        if result.get("status") in ("applied", "submitted"):
            pipeline_result = await session.execute(
                select(PipelineItem).where(
                    PipelineItem.brain_id == brain.brain_id,
                    PipelineItem.external_url == job_url.split("?")[0],
                )
            )
            pipeline_item = pipeline_result.scalar_one_or_none()
            if pipeline_item:
                pipeline_item.stage = "applied"
                pipeline_item.stage_order = 1
                history = pipeline_item.history_json or []
                history.append({"stage": "applied", "timestamp": datetime.utcnow().isoformat()})
                pipeline_item.history_json = history

        return {
            "summary": result.get("message", "Application processed"),
            "data": result,
        }

    async def _execute_generic_browser(
        self, page, browser_session, task: BrainTask, instructions: str,
    ) -> dict:
        """Execute a generic browser task using LLM for navigation decisions."""
        await browser_session.broadcast_status(f"Executing: {task.title}")

        # For generic browser tasks, navigate to the URL in instructions if any
        import re
        urls = re.findall(r'https?://\S+', instructions)
        if urls:
            await page.goto(urls[0], wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)

        return {
            "summary": f"Browser task completed: {task.title}",
            "data": {"instructions": instructions},
        }

    async def _run_agent(
        self, session: AsyncSession, task: BrainTask, brain: Brain,
    ) -> dict:
        """
        Execute the task using LLM text generation.
        For non-browser tasks (analysis, writing, etc.)
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

        try:
            from app.services.llm_service import get_active_llm_settings
            llm_settings = await get_active_llm_settings(session)
        except Exception:
            llm_settings = None

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
