"""Memory service - generates and retrieves agent execution memories."""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.memory import AgentMemory

logger = logging.getLogger(__name__)

SUMMARIZE_PROMPT = """Summarize this agent execution in 2-3 concise sentences. Focus on what was accomplished, key findings, and any important data points.

Agent: {agent_name}
Status: {status}
Duration: {duration}ms
Nodes executed: {node_count}
Outputs: {outputs}

Summary:"""


async def save_execution_memory(
    session: AsyncSession,
    agent_id: str,
    execution_id: str,
    agent_name: str,
    status: str,
    duration_ms: int,
    node_count: int,
    key_outputs: dict,
) -> None:
    """Generate a summary of the execution and store it as agent memory."""
    outputs_str = str(key_outputs)[:1000]

    summary = f"Execution {status} in {duration_ms}ms with {node_count} nodes."

    # If we have an OpenAI key, generate a better summary
    if settings.OPENAI_API_KEY and settings.OPENAI_API_KEY != "sk-proj-your-key-here":
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            prompt = SUMMARIZE_PROMPT.format(
                agent_name=agent_name,
                status=status,
                duration=duration_ms,
                node_count=node_count,
                outputs=outputs_str,
            )
            resp = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.3,
            )
            summary = resp.choices[0].message.content or summary
        except Exception as e:
            logger.warning("Failed to generate memory summary: %s", e)

    memory = AgentMemory(
        agent_id=agent_id,
        execution_id=execution_id,
        summary=summary,
        key_outputs=key_outputs,
        memory_type="execution_summary",
    )
    session.add(memory)
    await session.flush()
    logger.info("Saved memory for agent %s: %s...", agent_id, summary[:80])


async def get_agent_context(
    session: AsyncSession, agent_id: str, limit: int = 10
) -> str:
    """Get formatted context from agent's past memories for prompt injection."""
    result = await session.execute(
        select(AgentMemory)
        .where(AgentMemory.agent_id == agent_id)
        .order_by(AgentMemory.created_at.desc())
        .limit(limit)
    )
    memories = result.scalars().all()

    if not memories:
        return ""

    lines = ["Previous execution context (most recent first):"]
    for mem in memories:
        time_str = (
            mem.created_at.strftime("%Y-%m-%d %H:%M") if mem.created_at else "unknown"
        )
        lines.append(f"- [{time_str}] {mem.summary}")

    return "\n".join(lines)
