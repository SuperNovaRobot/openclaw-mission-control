"""Schemas for task template CRUD payloads."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlmodel import SQLModel


class TaskTemplateCreate(SQLModel):
    """Payload for creating a task template."""

    name: str
    title_template: str = ""
    description_template: str | None = None
    board_id: UUID | None = None


class TaskTemplateUpdate(SQLModel):
    """Payload for partial template updates."""

    name: str | None = None
    title_template: str | None = None
    description_template: str | None = None
    board_id: UUID | None = None


class TaskTemplateRead(SQLModel):
    """Template payload returned from read endpoints."""

    id: UUID
    organization_id: UUID
    board_id: UUID | None
    name: str
    title_template: str
    description_template: str | None
    created_from_task_id: UUID | None
    created_at: datetime
    updated_at: datetime
