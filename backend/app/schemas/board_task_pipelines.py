"""Schemas for board task pipeline CRUD payloads."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlmodel import SQLModel


class BoardTaskPipelineCreate(SQLModel):
    """Payload for creating a task pipeline."""

    target_board_id: UUID
    trigger_status: str = "done"
    task_title_template: str = ""
    task_description_template: str | None = None
    target_agent_id: UUID | None = None
    enabled: bool = True


class BoardTaskPipelineUpdate(SQLModel):
    """Payload for partial pipeline updates."""

    target_board_id: UUID | None = None
    trigger_status: str | None = None
    task_title_template: str | None = None
    task_description_template: str | None = None
    target_agent_id: UUID | None = None
    enabled: bool | None = None


class BoardTaskPipelineRead(SQLModel):
    """Pipeline payload returned from read endpoints."""

    id: UUID
    source_board_id: UUID
    target_board_id: UUID
    trigger_status: str
    enabled: bool
    task_title_template: str
    task_description_template: str | None
    target_agent_id: UUID | None
    created_at: datetime
    updated_at: datetime
