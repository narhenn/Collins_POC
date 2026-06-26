from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.agent import Agent
from app.models.execution import Execution
from app.models.user import User

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

DB = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


class DashboardStats(BaseModel):
    total_agents: int
    active_agents: int
    tasks_completed: int
    estimated_savings: float
    avg_response_time: Optional[float] = None


class ActivityEvent(BaseModel):
    execution_id: str
    agent_id: str
    agent_name: str
    agent_type: str
    status: str
    triggered_by: str
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    total_cost: Optional[float] = None
    created_at: datetime


@router.get("/stats", response_model=DashboardStats)
async def get_stats(db: DB, current_user: CurrentUser):
    # Total and active agents
    agent_result = await db.execute(
        select(
            func.count(Agent.id),
            func.count(Agent.id).filter(Agent.status == "active"),
        ).where(Agent.user_id == current_user.id)
    )
    agent_row = agent_result.one()
    total_agents = agent_row[0] or 0
    active_agents = agent_row[1] or 0

    # Tasks completed + avg response time
    exec_result = await db.execute(
        select(
            func.count(Execution.id).filter(Execution.status == "success"),
            func.avg(Execution.duration_ms),
        ).where(Execution.agent_id.in_(select(Agent.id).where(Agent.user_id == current_user.id)))
    )
    exec_row = exec_result.one()
    tasks_completed = exec_row[0] or 0
    avg_response_time = round(float(exec_row[1]), 1) if exec_row[1] is not None else None

    # Estimated savings: tasks_completed * 0.5 hours * $50/hr
    estimated_savings = tasks_completed * 0.5 * 50

    return DashboardStats(
        total_agents=total_agents,
        active_agents=active_agents,
        tasks_completed=tasks_completed,
        estimated_savings=estimated_savings,
        avg_response_time=avg_response_time,
    )


@router.get("/activity", response_model=list[ActivityEvent])
async def get_activity(db: DB, current_user: CurrentUser):
    result = await db.execute(
        select(Execution, Agent.name, Agent.type)
        .join(Agent, Execution.agent_id == Agent.id)
        .where(Agent.user_id == current_user.id)
        .order_by(Execution.created_at.desc())
        .limit(20)
    )
    rows = result.all()

    events = []
    for execution, agent_name, agent_type in rows:
        events.append(
            ActivityEvent(
                execution_id=str(execution.id),
                agent_id=str(execution.agent_id),
                agent_name=agent_name,
                agent_type=agent_type,
                status=execution.status,
                triggered_by=execution.triggered_by,
                started_at=execution.started_at,
                ended_at=execution.ended_at,
                duration_ms=execution.duration_ms,
                total_cost=float(execution.total_cost) if execution.total_cost else None,
                created_at=execution.created_at,
            )
        )

    return events
