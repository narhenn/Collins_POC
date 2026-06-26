import uuid

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class Agent(Base):
    __tablename__ = "agents"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_agent_user_name"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="draft", server_default="draft")
    schedule_cron: Mapped[str | None] = mapped_column(String(100), nullable=True)
    schedule_timezone: Mapped[str] = mapped_column(
        String(50), default="UTC", server_default="UTC"
    )
    created_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    last_execution_at = mapped_column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="agents")
    workflow = relationship(
        "Workflow", back_populates="agent", uselist=False, cascade="all, delete-orphan"
    )
    executions = relationship(
        "Execution", back_populates="agent", cascade="all, delete-orphan"
    )
