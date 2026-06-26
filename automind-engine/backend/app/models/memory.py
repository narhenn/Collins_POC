"""Agent Memory - stores execution summaries for cross-run context."""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class AgentMemory(Base):
    __tablename__ = "agent_memory"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    agent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    execution_id = Column(
        UUID(as_uuid=True),
        ForeignKey("executions.id", ondelete="SET NULL"),
        nullable=True,
    )
    summary = Column(Text, nullable=False)
    key_outputs = Column(JSONB, default=dict, server_default="{}")
    memory_type = Column(
        String(50), default="execution_summary", server_default="execution_summary"
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
