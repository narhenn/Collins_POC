from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, status, Depends
from typing import Annotated
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.template import AgentTemplate

router = APIRouter(prefix="/api/templates", tags=["templates"])

DB = Annotated[AsyncSession, Depends(get_db)]


class TemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: Optional[str] = None
    type: str
    workflow_definition: dict
    icon: Optional[str] = None
    color: Optional[str] = None
    features: list
    created_at: datetime


def _template_to_response(template: AgentTemplate) -> TemplateResponse:
    return TemplateResponse(
        id=str(template.id),
        name=template.name,
        description=template.description,
        type=template.type,
        workflow_definition=template.workflow_definition or {},
        icon=template.icon,
        color=template.color,
        features=template.features or [],
        created_at=template.created_at,
    )


@router.get("", response_model=list[TemplateResponse])
async def list_templates(db: DB):
    result = await db.execute(
        select(AgentTemplate).order_by(AgentTemplate.name)
    )
    templates = result.scalars().all()
    return [_template_to_response(t) for t in templates]


@router.get("/{template_id}", response_model=TemplateResponse)
async def get_template(template_id: str, db: DB):
    result = await db.execute(
        select(AgentTemplate).where(AgentTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )
    return _template_to_response(template)
