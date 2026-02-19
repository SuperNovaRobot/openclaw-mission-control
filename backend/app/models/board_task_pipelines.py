"""Board task pipeline configuration model."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlmodel import Field, Text

from app.core.time import utcnow
from app.models.base import QueryModel

RUNTIME_ANNOTATION_TYPES = (datetime,)


class BoardTaskPipeline(QueryModel, table=True):
    """Pipeline rule that creates a downstream task when a source task reaches a trigger status."""

    __tablename__ = "board_task_pipelines"  # pyright: ignore[reportAssignmentType]

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    source_board_id: UUID = Field(foreign_key="boards.id", index=True)
    target_board_id: UUID = Field(foreign_key="boards.id", index=True)
    trigger_status: str = Field(default="done", index=True)
    enabled: bool = Field(default=True, index=True)
    task_title_template: str = Field(default="")
    task_description_template: str | None = Field(default=None, sa_type=Text)
    target_agent_id: UUID | None = Field(default=None, foreign_key="agents.id", index=True)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
