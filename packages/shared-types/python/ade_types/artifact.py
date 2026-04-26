from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class CodeArtifact(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_id: UUID
    task_id: UUID
    file_path: str
    content: str
    diff: str | None = None
    language: str
    version: int
    created_at: datetime


class ExecutionResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_id: UUID
    task_id: UUID
    command: str
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int
    sandbox_id: str
    created_at: datetime
