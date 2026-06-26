import uuid

from sqlalchemy import DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class Workflow(Base):
    __tablename__ = "workflows"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(50), default="draft", server_default="draft"
    )
    definition = mapped_column(JSONB, default=dict, server_default="{}", nullable=False)
    created_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    deployed_at = mapped_column(DateTime(timezone=True), nullable=True)

    agent = relationship("Agent", back_populates="workflow")
