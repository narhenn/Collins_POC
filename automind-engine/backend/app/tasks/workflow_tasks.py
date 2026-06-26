import asyncio
import logging

from celery import shared_task
from sqlalchemy import select

from app.engine.executor import WorkflowExecutor

logger = logging.getLogger(__name__)


@shared_task(name="execute_workflow")
def execute_workflow_task(
    execution_id: str, workflow_definition: dict,
    init_variables: dict | None = None,
) -> dict:
    """Celery task to execute a workflow.

    Celery tasks are synchronous, so we use asyncio.run() to drive the async
    executor. init_variables are runtime vars injected from the trigger.
    """
    try:
        result = asyncio.run(_execute(execution_id, workflow_definition, init_variables))
        return {"status": "completed", "execution_id": execution_id}
    except Exception as exc:
        logger.exception("Workflow execution failed for %s", execution_id)
        # Try to mark execution as failed in the DB
        try:
            asyncio.run(_mark_failed(execution_id, str(exc)))
        except Exception:
            logger.exception("Could not mark execution %s as failed", execution_id)
        return {"status": "failed", "execution_id": execution_id, "error": str(exc)}


async def _execute(
    execution_id: str, workflow_definition: dict,
    init_variables: dict | None = None,
) -> dict:
    # Create a fresh engine for this event loop (asyncpg engines are not reusable across loops)
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from app.core.config import settings

    engine = create_async_engine(settings.async_database_url, pool_size=5)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        executor = WorkflowExecutor(
            execution_id, workflow_definition,
            variables=init_variables,
            session_factory=session_factory,
        )
        return await executor.execute()
    finally:
        await engine.dispose()


async def _mark_failed(execution_id: str, error_message: str) -> None:
    from datetime import datetime, timezone
    from sqlalchemy import select
    from app.core.database import async_session
    from app.models.execution import Execution

    async with async_session() as session:
        result = await session.execute(
            select(Execution).where(Execution.id == execution_id)
        )
        execution = result.scalar_one_or_none()
        if execution and execution.status != "failed":
            execution.status = "failed"
            execution.error_message = error_message
            execution.ended_at = datetime.now(timezone.utc)
            await session.commit()


@shared_task(name="execute_workflow_scheduled")
def execute_workflow_scheduled_task(agent_id: str) -> dict:
    """Celery task for scheduled (cron-triggered) agent runs."""
    try:
        result = asyncio.run(_execute_scheduled(agent_id))
        return {"status": "completed", "agent_id": agent_id}
    except Exception as exc:
        logger.exception("Scheduled execution failed for agent %s", agent_id)
        return {"status": "failed", "agent_id": agent_id, "error": str(exc)}


async def _execute_scheduled(agent_id: str) -> dict:
    """Look up agent + workflow, create execution, run it."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from app.core.config import settings
    from app.models.agent import Agent
    from app.models.workflow import Workflow
    from app.models.execution import Execution

    engine = create_async_engine(settings.async_database_url, pool_size=5)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        # Get agent
        result = await session.execute(select(Agent).where(Agent.id == agent_id))
        agent = result.scalar_one_or_none()
        if not agent or agent.status != "active":
            logger.info("Skipping scheduled run: agent %s is %s", agent_id, agent.status if agent else "missing")
            return {}

        # Get workflow
        result = await session.execute(select(Workflow).where(Workflow.agent_id == agent_id))
        workflow = result.scalar_one_or_none()
        if not workflow or not workflow.definition or not workflow.definition.get("nodes"):
            logger.info("Skipping scheduled run: agent %s has no valid workflow", agent_id)
            return {}

        # Create execution
        execution = Execution(
            agent_id=agent.id,
            workflow_id=workflow.id,
            status="pending",
            triggered_by="schedule",
            variables={},
        )
        session.add(execution)
        await session.flush()
        execution_id = str(execution.id)
        workflow_definition = workflow.definition
        await session.commit()

    # Run executor with fresh session factory
    try:
        executor = WorkflowExecutor(execution_id, workflow_definition, session_factory=session_factory)
        return await executor.execute()
    finally:
        await engine.dispose()
