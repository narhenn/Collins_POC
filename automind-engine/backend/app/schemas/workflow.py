from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class WorkflowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    agent_id: str
    status: str
    definition: dict
    created_at: datetime
    updated_at: datetime
    deployed_at: Optional[datetime] = None


class WorkflowUpdate(BaseModel):
    definition: dict
