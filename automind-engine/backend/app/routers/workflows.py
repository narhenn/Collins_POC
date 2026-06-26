from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.agent import Agent
from app.models.user import User
from app.models.workflow import Workflow
from app.schemas.workflow import WorkflowResponse, WorkflowUpdate
from app.services.scheduler_service import schedule_agent, unschedule_agent

router = APIRouter(prefix="/api/agents", tags=["workflows"])

DB = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


def _workflow_to_response(workflow: Workflow) -> WorkflowResponse:
    return WorkflowResponse(
        id=str(workflow.id),
        agent_id=str(workflow.agent_id),
        status=workflow.status,
        definition=workflow.definition or {},
        created_at=workflow.created_at,
        updated_at=workflow.updated_at,
        deployed_at=workflow.deployed_at,
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


async def _get_workflow_or_404(db: AsyncSession, agent_id) -> Workflow:
    result = await db.execute(
        select(Workflow).where(Workflow.agent_id == agent_id)
    )
    workflow = result.scalar_one_or_none()
    if workflow is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found for this agent",
        )
    return workflow


@router.get("/{agent_id}/workflow", response_model=WorkflowResponse)
async def get_workflow(agent_id: str, db: DB, current_user: CurrentUser):
    await _get_agent_or_404(db, agent_id, current_user.id)
    workflow = await _get_workflow_or_404(db, agent_id)
    return _workflow_to_response(workflow)


@router.put("/{agent_id}/workflow", response_model=WorkflowResponse)
async def update_workflow(agent_id: str, data: WorkflowUpdate, db: DB, current_user: CurrentUser):
    await _get_agent_or_404(db, agent_id, current_user.id)
    workflow = await _get_workflow_or_404(db, agent_id)

    workflow.definition = data.definition
    await db.flush()
    await db.refresh(workflow)

    return _workflow_to_response(workflow)


@router.post("/{agent_id}/workflow/deploy", response_model=WorkflowResponse)
async def deploy_workflow(agent_id: str, db: DB, current_user: CurrentUser):
    agent = await _get_agent_or_404(db, agent_id, current_user.id)
    workflow = await _get_workflow_or_404(db, agent_id)

    workflow.status = "active"
    workflow.deployed_at = datetime.now(timezone.utc)
    agent.status = "active"
    await db.flush()
    await db.refresh(workflow)

    # Schedule the agent if it has a cron expression
    if agent.schedule_cron:
        schedule_agent(str(agent.id), agent.schedule_cron, agent.schedule_timezone)

    return _workflow_to_response(workflow)
