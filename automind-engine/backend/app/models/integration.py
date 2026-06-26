import uuid

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class Integration(Base):
    __tablename__ = "integrations"
    __table_args__ = (
        UniqueConstraint("user_id", "service", name="uq_integration_user_service"),
    )

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
    service: Mapped[str] = mapped_column(String(100), nullable=False)
    config = mapped_column(JSONB, default=dict, server_default="{}", nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), default="active", server_default="active"
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

    user = relationship("User", back_populates="integrations")
