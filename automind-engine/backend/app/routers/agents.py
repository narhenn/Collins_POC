import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.agent import Agent
from app.models.execution import Execution
from app.models.template import AgentTemplate
from app.models.user import User
from app.models.workflow import Workflow
from app.schemas.agent import (
    AgentCreate,
    AgentResponse,
    AgentUpdate,
)
from app.services.agent_generator import generate_agent_from_description
from app.services.scheduler_service import schedule_agent, unschedule_agent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agents", tags=["agents"])

DB = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


def _agent_to_response(agent: Agent, total_executions: int, success_rate: float | None) -> AgentResponse:
    return AgentResponse(
        id=str(agent.id),
        user_id=str(agent.user_id),
        name=agent.name,
        description=agent.description,
        type=agent.type,
        status=agent.status,
        schedule_cron=agent.schedule_cron,
        schedule_timezone=agent.schedule_timezone,
        created_at=agent.created_at,
        updated_at=agent.updated_at,
        last_execution_at=agent.last_execution_at,
        total_executions=total_executions,
        success_rate=success_rate,
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


async def _get_agent_stats(db: AsyncSession, agent_id) -> tuple[int, float | None]:
    result = await db.execute(
        select(
            func.count(Execution.id),
            func.avg(
                case(
                    (Execution.status == "success", 1.0),
                    (Execution.status == "failed", 0.0),
                )
            ),
        ).where(Execution.agent_id == agent_id)
    )
    row = result.one()
    total = row[0] or 0
    success_rate = round(float(row[1]) * 100, 1) if row[1] is not None else None
    return total, success_rate


@router.get("", response_model=list[AgentResponse])
async def list_agents(db: DB, current_user: CurrentUser):
    result = await db.execute(
        select(Agent).where(Agent.user_id == current_user.id).order_by(Agent.created_at.desc())
    )
    agents = result.scalars().all()

    agent_responses = []
    for agent in agents:
        total, success_rate = await _get_agent_stats(db, agent.id)
        agent_responses.append(_agent_to_response(agent, total, success_rate))

    return agent_responses


@router.post("", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(data: AgentCreate, db: DB, current_user: CurrentUser):
    agent = Agent(
        user_id=current_user.id,
        name=data.name,
        type=data.type,
        description=data.description,
    )
    db.add(agent)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An agent named '{data.name}' already exists",
        )

    # Create workflow
    workflow_definition: dict = {"nodes": [], "edges": [], "viewport": {"x": 0, "y": 0, "zoom": 1}}
    if data.template_id:
        result = await db.execute(
            select(AgentTemplate).where(AgentTemplate.id == data.template_id)
        )
        template = result.scalar_one_or_none()
        if template and template.workflow_definition:
            workflow_definition = template.workflow_definition

    workflow = Workflow(
        agent_id=agent.id,
        definition=workflow_definition,
    )
    db.add(workflow)
    await db.flush()
    await db.refresh(agent)

    return _agent_to_response(agent, 0, None)


class GenerateAgentRequest(BaseModel):
    description: str


@router.post("/generate", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def generate_agent(data: GenerateAgentRequest, db: DB, current_user: CurrentUser):
    """Generate a complete agent workflow from a natural language description."""
    if not data.description.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Description is required",
        )

    try:
        result = await generate_agent_from_description(data.description)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except Exception as exc:
        logger.exception("Agent generation failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate agent: {exc}",
        )

    # Create agent from generated result
    agent_name = result.get("agent_name", "Generated Agent")
    agent_type = result.get("agent_type", "custom")
    agent_description = result.get("agent_description", data.description)

    # Validate agent_type
    if agent_type not in ("sales", "marketing", "support", "custom"):
        agent_type = "custom"

    agent = Agent(
        user_id=current_user.id,
        name=agent_name,
        type=agent_type,
        description=agent_description,
    )

    # Apply schedule if provided
    schedule = result.get("schedule", {})
    if schedule.get("cron"):
        agent.schedule_cron = schedule["cron"]
    if schedule.get("timezone"):
        agent.schedule_timezone = schedule["timezone"]

    db.add(agent)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An agent named '{agent_name}' already exists",
        )

    # Create workflow with generated definition
    workflow_definition = result.get("workflow", {"nodes": [], "edges": [], "viewport": {"x": 0, "y": 0, "zoom": 1}})
    workflow = Workflow(
        agent_id=agent.id,
        definition=workflow_definition,
    )
    db.add(workflow)
    await db.flush()
    await db.refresh(agent)

    return _agent_to_response(agent, 0, None)


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: str, db: DB, current_user: CurrentUser):
    agent = await _get_agent_or_404(db, agent_id, current_user.id)
    total, success_rate = await _get_agent_stats(db, agent.id)
    return _agent_to_response(agent, total, success_rate)


@router.patch("/{agent_id}", response_model=AgentResponse)
async def update_agent(agent_id: str, data: AgentUpdate, db: DB, current_user: CurrentUser):
    agent = await _get_agent_or_404(db, agent_id, current_user.id)

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(agent, field, value)

    await db.flush()
    await db.refresh(agent)

    total, success_rate = await _get_agent_stats(db, agent.id)
    return _agent_to_response(agent, total, success_rate)


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(agent_id: str, db: DB, current_user: CurrentUser):
    agent = await _get_agent_or_404(db, agent_id, current_user.id)
    unschedule_agent(str(agent.id))
    await db.delete(agent)
    await db.flush()


@router.post("/{agent_id}/pause", response_model=AgentResponse)
async def pause_agent(agent_id: str, db: DB, current_user: CurrentUser):
    agent = await _get_agent_or_404(db, agent_id, current_user.id)
    agent.status = "paused"
    unschedule_agent(str(agent.id))
    await db.flush()
    await db.refresh(agent)

    total, success_rate = await _get_agent_stats(db, agent.id)
    return _agent_to_response(agent, total, success_rate)


@router.post("/{agent_id}/resume", response_model=AgentResponse)
async def resume_agent(agent_id: str, db: DB, current_user: CurrentUser):
    agent = await _get_agent_or_404(db, agent_id, current_user.id)
    agent.status = "active"
    if agent.schedule_cron:
        schedule_agent(str(agent.id), agent.schedule_cron, agent.schedule_timezone)
    await db.flush()
    await db.refresh(agent)

    total, success_rate = await _get_agent_stats(db, agent.id)
    return _agent_to_response(agent, total, success_rate)
