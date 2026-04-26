from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class Project(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    repo_url: str | None = None
    repo_path: str | None = None
    settings: dict[str, Any] = {}
    created_at: datetime
    updated_at: datetime


class ContextChunk(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    file_path: str
    chunk_content: str
    embedding: list[float] | None = None
    metadata: dict[str, Any] = {}
    indexed_at: datetime


class WorkflowEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_type: str
    step_id: UUID | None = None
    payload: dict[str, Any] = {}
    timestamp: int


class ConversationMessage(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: UUID
    role: Literal["user", "assistant", "system", "tool"]
    content: str
    metadata: dict[str, Any] = {}
    created_at: datetime
