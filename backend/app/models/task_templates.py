"""Task template model for reusable task configurations."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlmodel import Field, Text

from app.core.time import utcnow
from app.models.base import QueryModel

RUNTIME_ANNOTATION_TYPES = (datetime,)


class TaskTemplate(QueryModel, table=True):
    """Reusable task title + description template scoped to a board or org-wide."""

    __tablename__ = "task_templates"  # pyright: ignore[reportAssignmentType]

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(foreign_key="organizations.id", index=True)
    board_id: UUID | None = Field(default=None, foreign_key="boards.id", index=True)
    name: str = Field(default="")
    title_template: str = Field(default="")
    description_template: str | None = Field(default=None, sa_type=Text)
    created_from_task_id: UUID | None = Field(default=None)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
