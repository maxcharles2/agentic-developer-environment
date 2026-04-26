from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from .task import AgentType


class AgentRunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


class AgentRun(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: UUID
    step_id: UUID | None = None
    agent_type: AgentType
    model: str
    status: AgentRunStatus
    input_state: dict[str, Any] = {}
    output_state: dict[str, Any] = {}
    tokens_in: int | None = None
    tokens_out: int | None = None
    latency_ms: int | None = None
    retry_count: int = 0
    created_at: datetime


class AgentMetric(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_id: UUID
    agent_type: AgentType
    metric_name: str
    metric_value: float
    labels: dict[str, Any] = {}
    recorded_at: datetime
