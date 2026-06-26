import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class Execution(Base):
    __tablename__ = "executions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflows.id"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(50), default="pending", server_default="pending"
    )
    triggered_by: Mapped[str] = mapped_column(String(50), nullable=False)
    started_at = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    variables = mapped_column(JSONB, default=dict, server_default="{}", nullable=False)
    total_cost = mapped_column(
        Numeric(10, 6), default=0, server_default="0", nullable=False
    )
    created_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    node_logs = relationship(
        "ExecutionNodeLog", back_populates="execution", cascade="all, delete-orphan"
    )
    agent = relationship("Agent", back_populates="executions")


class ExecutionNodeLog(Base):
    __tablename__ = "execution_node_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    execution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("executions.id", ondelete="CASCADE"),
        nullable=False,
    )
    node_id: Mapped[str] = mapped_column(String(255), nullable=False)
    node_type: Mapped[str] = mapped_column(String(50), nullable=False)
    node_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), default="pending", server_default="pending"
    )
    started_at = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms = mapped_column(Integer, nullable=True)
    input_data = mapped_column(JSONB, default=dict, server_default="{}", nullable=False)
    output_data = mapped_column(JSONB, default=dict, server_default="{}", nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_usage = mapped_column(JSONB, nullable=True)
    created_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    execution = relationship("Execution", back_populates="node_logs")
