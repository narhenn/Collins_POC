import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.agent import Agent
from app.models.user import User
from app.services.memory_service import get_agent_context

router = APIRouter(prefix="/api/agents", tags=["chat"])

DB = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]

logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []  # [{"role": "user"|"assistant", "content": "..."}]


@router.post("/{agent_id}/chat")
async def chat_with_agent(
    agent_id: str,
    req: ChatRequest,
    db: DB,
    current_user: CurrentUser,
    request: Request,
):
    """Stream a chat response from the agent using its execution memory as context."""
    # Verify agent ownership
    result = await db.execute(
        select(Agent).where(Agent.id == agent_id, Agent.user_id == current_user.id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Get agent memory context
    memory_context = await get_agent_context(db, agent_id, limit=15)

    system_prompt = f"""You are "{agent.name}", an AI agent on the GoalCert AutoMind platform.
Type: {agent.type}
Description: {agent.description or 'No description'}
Status: {agent.status}
Schedule: {agent.schedule_cron or 'Manual'}

{memory_context}

You have access to your past execution history above. Answer the user's questions about your work, findings, and status. Be helpful, concise, and reference specific data from your past executions when relevant. If asked to do something, explain that you can be configured through the workflow builder."""

    if not settings.OPENAI_API_KEY:
        # Non-streaming fallback
        return {"response": "Chat requires an OpenAI API key. Please configure it in Settings."}

    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    # Add conversation history (last 10 messages)
    for msg in req.history[-10:]:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": req.message})

    async def generate():
        try:
            stream = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                stream=True,
                max_tokens=1024,
                temperature=0.7,
            )
            async for chunk in stream:
                if await request.is_disconnected():
                    break
                delta = chunk.choices[0].delta
                if delta.content:
                    yield {"data": json.dumps({"type": "token", "content": delta.content})}
            yield {"data": json.dumps({"type": "done"})}
        except Exception as e:
            logger.exception("Chat streaming error")
            yield {"data": json.dumps({"type": "error", "content": str(e)})}

    return EventSourceResponse(generate())
