from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class AgentCreate(BaseModel):
    name: str = Field(min_length=2, max_length=50)
    type: Literal["sales", "marketing", "support", "custom"]
    description: Optional[str] = None
    template_id: Optional[str] = None


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    schedule_cron: Optional[str] = None
    schedule_timezone: Optional[str] = None


class AgentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    name: str
    description: Optional[str] = None
    type: str
    status: str
    schedule_cron: Optional[str] = None
    schedule_timezone: str
    created_at: datetime
    updated_at: datetime
    last_execution_at: Optional[datetime] = None
    success_rate: Optional[float] = None
    total_executions: Optional[int] = None


class AgentListResponse(BaseModel):
    agents: list[AgentResponse]
