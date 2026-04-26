from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TaskStatus(StrEnum):
    PENDING = "pending"
    PLANNING = "planning"
    EXECUTING = "executing"
    REVIEWING = "reviewing"
    COMPLETED = "completed"
    FAILED = "failed"


class StepStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class AgentType(StrEnum):
    PLANNER = "planner"
    CODEGEN = "codegen"
    EXECUTOR = "executor"
    CONTEXT = "context"


class TaskStep(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: UUID
    ordinal: int
    title: str
    description: str
    status: StepStatus
    agent_type: AgentType
    input_data: dict[str, Any] = {}
    output_data: dict[str, Any] = {}
    started_at: datetime | None = None
    completed_at: datetime | None = None


class Task(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    prompt: str
    status: TaskStatus
    metadata: dict[str, Any] = {}
    created_at: datetime
    updated_at: datetime
