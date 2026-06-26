from typing import Annotated

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from pydantic import BaseModel

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.agent import Agent
from app.models.execution import Execution, ExecutionNodeLog
from app.models.user import User
from app.models.workflow import Workflow
from app.schemas.execution import (
    ExecutionDetailResponse,
    ExecutionNodeLogResponse,
    ExecutionResponse,
)
from app.tasks.celery_app import celery_app


class ExecuteRequest(BaseModel):
    """Optional runtime variables to inject into the workflow execution."""
    variables: dict = {}

router = APIRouter(prefix="/api", tags=["executions"])

DB = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


# ---- helpers ----


def _execution_to_response(execution: Execution) -> ExecutionResponse:
    return ExecutionResponse(
        id=str(execution.id),
        agent_id=str(execution.agent_id),
        workflow_id=str(execution.workflow_id),
        status=execution.status,
        triggered_by=execution.triggered_by,
        started_at=execution.started_at,
        ended_at=execution.ended_at,
        duration_ms=execution.duration_ms,
        error_message=execution.error_message,
        variables=execution.variables or {},
        total_cost=execution.total_cost,
        created_at=execution.created_at,
    )


def _node_log_to_response(log: ExecutionNodeLog) -> ExecutionNodeLogResponse:
    return ExecutionNodeLogResponse(
        id=str(log.id),
        execution_id=str(log.execution_id),
        node_id=log.node_id,
        node_type=log.node_type,
        node_label=log.node_label,
        status=log.status,
        started_at=log.started_at,
        ended_at=log.ended_at,
        duration_ms=log.duration_ms,
        input_data=log.input_data or {},
        output_data=log.output_data or {},
        error_message=log.error_message,
        llm_usage=log.llm_usage,
        created_at=log.created_at,
    )


async def _get_agent_or_404(db: AsyncSession, agent_id: str, user_id) -> Agent:
    result = await db.execute(
        select(Agent).where(Agent.id == agent_id, Agent.user_id == user_id)
    )
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )
    return agent


async def _get_execution_for_user(
    db: AsyncSession, execution_id: str, user_id
) -> Execution:
    """Fetch an execution ensuring it belongs to the current user."""
    result = await db.execute(
        select(Execution)
        .join(Agent, Execution.agent_id == Agent.id)
        .where(Execution.id == execution_id, Agent.user_id == user_id)
    )
    execution = result.scalar_one_or_none()
    if execution is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Execution not found",
        )
    return execution


# ---- endpoints ----


@router.post(
    "/agents/{agent_id}/execute",
    response_model=ExecutionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_execution(
    agent_id: str, db: DB, current_user: CurrentUser,
    req: ExecuteRequest | None = None,
):
    """Manually trigger a workflow execution for the given agent.
    Optionally pass runtime variables that are injected into the workflow."""
    agent = await _get_agent_or_404(db, agent_id, current_user.id)
    init_vars = req.variables if req else {}

    # Get the agent's workflow
    result = await db.execute(
        select(Workflow).where(Workflow.agent_id == agent.id)
    )
    workflow = result.scalar_one_or_none()
    if workflow is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No workflow found for this agent",
        )

    if workflow.status not in ("active", "draft"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Workflow is {workflow.status}, must be active or draft to execute",
        )

    if not workflow.definition or not workflow.definition.get("nodes"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Workflow has no nodes defined",
        )

    # Create execution record with optional runtime variables
    execution = Execution(
        agent_id=agent.id,
        workflow_id=workflow.id,
        status="pending",
        triggered_by="manual",
        variables=init_vars,
    )
    db.add(execution)
    await db.flush()
    await db.refresh(execution)

    execution_id = str(execution.id)

    # Queue Celery task — pass runtime variables so they seed the executor
    celery_app.send_task(
        "execute_workflow",
        args=[execution_id, workflow.definition, init_vars],
    )

    return _execution_to_response(execution)


@router.get("/agents/{agent_id}/executions", response_model=list[ExecutionResponse])
async def list_executions(
    agent_id: str,
    db: DB,
    current_user: CurrentUser,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """List executions for a given agent, paginated, most recent first."""
    await _get_agent_or_404(db, agent_id, current_user.id)

    result = await db.execute(
        select(Execution)
        .where(Execution.agent_id == agent_id)
        .order_by(Execution.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    executions = result.scalars().all()
    return [_execution_to_response(e) for e in executions]


@router.get("/executions/{execution_id}", response_model=ExecutionDetailResponse)
async def get_execution(execution_id: str, db: DB, current_user: CurrentUser):
    """Get a single execution with its node logs."""
    execution = await _get_execution_for_user(db, execution_id, current_user.id)

    result = await db.execute(
        select(ExecutionNodeLog)
        .where(ExecutionNodeLog.execution_id == execution.id)
        .order_by(ExecutionNodeLog.created_at)
    )
    node_logs = result.scalars().all()

    return ExecutionDetailResponse(
        execution=_execution_to_response(execution),
        node_logs=[_node_log_to_response(log) for log in node_logs],
    )


@router.get(
    "/executions/{execution_id}/logs",
    response_model=list[ExecutionNodeLogResponse],
)
async def get_execution_logs(
    execution_id: str, db: DB, current_user: CurrentUser
):
    """Get node logs for an execution, ordered chronologically."""
    execution = await _get_execution_for_user(db, execution_id, current_user.id)

    result = await db.execute(
        select(ExecutionNodeLog)
        .where(ExecutionNodeLog.execution_id == execution.id)
        .order_by(ExecutionNodeLog.created_at)
    )
    node_logs = result.scalars().all()
    return [_node_log_to_response(log) for log in node_logs]


@router.get("/executions/{execution_id}/stream")
async def stream_execution(execution_id: str, request: Request):
    """SSE endpoint for real-time execution logs via Redis pub/sub.

    No auth required - execution IDs are UUIDs (unguessable).
    """
    r = aioredis.from_url(settings.REDIS_URL)
    pubsub = r.pubsub()
    channel = f"execution:{execution_id}:logs"
    await pubsub.subscribe(channel)

    async def event_generator():
        try:
            async for message in pubsub.listen():
                if await request.is_disconnected():
                    break
                if message["type"] == "message":
                    data = message["data"].decode()
                    yield {"data": data}
                    # Close stream when executor signals completion
                    if '"__STREAM_END__"' in data:
                        break
        finally:
            await pubsub.unsubscribe(channel)
            await r.aclose()

    return EventSourceResponse(event_generator())
