from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ExecutionNodeLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    execution_id: str
    node_id: str
    node_type: str
    node_label: Optional[str] = None
    status: str
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    input_data: dict
    output_data: dict
    error_message: Optional[str] = None
    llm_usage: Optional[dict] = None
    created_at: datetime


class ExecutionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    agent_id: str
    workflow_id: str
    status: str
    triggered_by: str
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    error_message: Optional[str] = None
    variables: dict
    total_cost: Decimal
    created_at: datetime


class ExecutionDetailResponse(BaseModel):
    execution: ExecutionResponse
    node_logs: list[ExecutionNodeLogResponse]
