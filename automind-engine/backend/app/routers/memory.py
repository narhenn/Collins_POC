"""Memory API - list and manage agent memories."""

import logging
from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.agent import Agent
from app.models.memory import AgentMemory
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agents", tags=["memory"])

DB = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


class MemoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    agent_id: str
    execution_id: Optional[str] = None
    summary: str
    key_outputs: dict = {}
    memory_type: str
    created_at: datetime


class MemoryListResponse(BaseModel):
    memories: list[MemoryResponse]
    total: int


async def _verify_agent_ownership(
    db: AsyncSession, agent_id: str, user_id
) -> Agent:
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


@router.get("/{agent_id}/memory", response_model=MemoryListResponse)
async def list_agent_memories(
    agent_id: str,
    db: DB,
    current_user: CurrentUser,
    limit: int = 20,
    offset: int = 0,
):
    """List memories for an agent, paginated."""
    await _verify_agent_ownership(db, agent_id, current_user.id)

    # Get total count
    count_result = await db.execute(
        select(func.count(AgentMemory.id)).where(AgentMemory.agent_id == agent_id)
    )
    total = count_result.scalar() or 0

    # Get paginated memories
    result = await db.execute(
        select(AgentMemory)
        .where(AgentMemory.agent_id == agent_id)
        .order_by(AgentMemory.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    memories = result.scalars().all()

    return MemoryListResponse(
        memories=[
            MemoryResponse(
                id=str(m.id),
                agent_id=str(m.agent_id),
                execution_id=str(m.execution_id) if m.execution_id else None,
                summary=m.summary,
                key_outputs=m.key_outputs or {},
                memory_type=m.memory_type,
                created_at=m.created_at,
            )
            for m in memories
        ],
        total=total,
    )


@router.delete("/{agent_id}/memory", status_code=status.HTTP_204_NO_CONTENT)
async def clear_agent_memories(
    agent_id: str,
    db: DB,
    current_user: CurrentUser,
):
    """Clear all memories for an agent."""
    await _verify_agent_ownership(db, agent_id, current_user.id)

    await db.execute(
        delete(AgentMemory).where(AgentMemory.agent_id == agent_id)
    )
    await db.flush()
