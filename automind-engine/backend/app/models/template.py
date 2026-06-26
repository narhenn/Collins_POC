import uuid

from sqlalchemy import DateTime, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class AgentTemplate(Base):
    __tablename__ = "agent_templates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    workflow_definition = mapped_column(JSONB, nullable=False)
    icon: Mapped[str | None] = mapped_column(String(50), nullable=True)
    color: Mapped[str | None] = mapped_column(String(50), nullable=True)
    features = mapped_column(JSONB, default=list, server_default="[]", nullable=False)
    created_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
