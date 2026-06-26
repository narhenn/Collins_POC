from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class IntegrationCreate(BaseModel):
    service: str
    config: dict


class IntegrationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    service: str
    config: dict
    status: str
    created_at: datetime
    updated_at: datetime
