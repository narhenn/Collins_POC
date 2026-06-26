from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.integration import Integration
from app.models.user import User
from app.schemas.integration import IntegrationCreate, IntegrationResponse

router = APIRouter(prefix="/api/integrations", tags=["integrations"])

DB = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]

ALLOWED_SERVICES = {"resend", "slack"}

SENSITIVE_KEYS = {"api_key", "webhook_url", "secret", "token"}


def _mask_config(config: dict) -> dict:
    """Mask sensitive values in integration config before returning to client."""
    masked = {}
    for key, value in config.items():
        if key in SENSITIVE_KEYS and isinstance(value, str):
            if key == "webhook_url":
                try:
                    from urllib.parse import urlparse

                    parsed = urlparse(value)
                    masked[key] = f"{parsed.scheme}://{parsed.netloc}/****"
                except Exception:
                    masked[key] = "****"
            else:
                # Show last 4 chars for keys/tokens
                if len(value) > 4:
                    masked[key] = "****" + value[-4:]
                else:
                    masked[key] = "****"
        else:
            masked[key] = value
    return masked


def _integration_to_response(integration: Integration, mask: bool = True) -> IntegrationResponse:
    config = dict(integration.config) if integration.config else {}
    if mask:
        config = _mask_config(config)
    return IntegrationResponse(
        id=str(integration.id),
        user_id=str(integration.user_id),
        service=integration.service,
        config=config,
        status=integration.status,
        created_at=integration.created_at,
        updated_at=integration.updated_at,
    )


@router.get("", response_model=list[IntegrationResponse])
async def list_integrations(db: DB, current_user: CurrentUser):
    result = await db.execute(
        select(Integration)
        .where(Integration.user_id == current_user.id)
        .order_by(Integration.created_at.desc())
    )
    integrations = result.scalars().all()
    return [_integration_to_response(i) for i in integrations]


@router.post("", response_model=IntegrationResponse, status_code=status.HTTP_201_CREATED)
async def connect_integration(data: IntegrationCreate, db: DB, current_user: CurrentUser):
    if data.service not in ALLOWED_SERVICES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Service must be one of: {', '.join(sorted(ALLOWED_SERVICES))}",
        )

    # Check if integration already exists (upsert)
    result = await db.execute(
        select(Integration).where(
            Integration.user_id == current_user.id,
            Integration.service == data.service,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.config = data.config
        existing.status = "active"
        await db.flush()
        await db.refresh(existing)
        return _integration_to_response(existing)

    integration = Integration(
        user_id=current_user.id,
        service=data.service,
        config=data.config,
        status="active",
    )
    db.add(integration)
    await db.flush()
    await db.refresh(integration)
    return _integration_to_response(integration)


@router.delete("/{integration_id}", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_integration(integration_id: str, db: DB, current_user: CurrentUser):
    result = await db.execute(
        select(Integration).where(
            Integration.id == integration_id,
            Integration.user_id == current_user.id,
        )
    )
    integration = result.scalar_one_or_none()

    if integration is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Integration not found",
        )

    await db.delete(integration)
    await db.flush()
