"""Task pipeline evaluation and execution service."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from uuid import UUID

from sqlmodel import col, select

from app.core.logging import get_logger
from app.core.time import utcnow
from app.models.agents import Agent
from app.models.board_task_pipelines import BoardTaskPipeline
from app.models.boards import Board
from app.models.tasks import Task

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

logger = get_logger(__name__)

_TEMPLATE_VAR_RE = re.compile(r"\{\{(\w+(?:\.\w+)*)\}\}")


def render_pipeline_template(template: str, context: dict[str, str]) -> str:
    """Substitute ``{{var.name}}`` placeholders with flat context values."""
    if not template:
        return template

    def _replacer(match: re.Match[str]) -> str:
        key = match.group(1)
        return context.get(key, match.group(0))

    return _TEMPLATE_VAR_RE.sub(_replacer, template)


def build_template_context(
    task: Task,
    source_board: Board,
    agent: Agent | None,
) -> dict[str, str]:
    """Build a flat dict of template variables from a completed task."""
    return {
        "source_task.title": task.title or "",
        "source_task.description": task.description or "",
        "source_task.id": str(task.id),
        "source_board.name": source_board.name or "",
        "source_task.agent_name": agent.name if agent else "",
    }


async def evaluate_pipelines(
    session: AsyncSession,
    task: Task,
    new_status: str,
) -> list[Task]:
    """Find matching pipelines and create downstream tasks.

    Returns a list of newly created tasks.  Skips evaluation when the
    source task was itself auto-created (loop guard).
    """
    if task.auto_created:
        logger.debug(
            "pipeline.skip_auto_created",
            extra={"task_id": str(task.id)},
        )
        return []

    if task.board_id is None:
        return []

    query = select(BoardTaskPipeline).where(
        col(BoardTaskPipeline.source_board_id) == task.board_id,
        col(BoardTaskPipeline.trigger_status) == new_status,
        col(BoardTaskPipeline.enabled).is_(True),
    )
    result = await session.exec(query)
    pipelines = result.all()
    if not pipelines:
        return []

    source_board = await session.get(Board, task.board_id)
    if source_board is None:
        return []

    agent: Agent | None = None
    if task.assigned_agent_id:
        agent = await session.get(Agent, task.assigned_agent_id)

    context = build_template_context(task, source_board, agent)
    created_tasks: list[Task] = []

    for pipeline in pipelines:
        try:
            new_task = await _execute_pipeline(session, pipeline, context)
            created_tasks.append(new_task)
        except Exception:
            logger.exception(
                "pipeline.execute_failed",
                extra={
                    "pipeline_id": str(pipeline.id),
                    "task_id": str(task.id),
                },
            )

    return created_tasks


async def _execute_pipeline(
    session: AsyncSession,
    pipeline: BoardTaskPipeline,
    context: dict[str, str],
) -> Task:
    """Render templates and create a downstream task on the target board."""
    title = render_pipeline_template(pipeline.task_title_template, context)
    if not title.strip():
        title = f"Pipeline task from {context.get('source_board.name', 'unknown')}"

    description = None
    if pipeline.task_description_template:
        description = render_pipeline_template(pipeline.task_description_template, context)

    now = utcnow()
    new_task = Task(
        board_id=pipeline.target_board_id,
        title=title,
        description=description,
        status="inbox",
        priority="medium",
        assigned_agent_id=pipeline.target_agent_id,
        auto_created=True,
        auto_reason=f"pipeline:{pipeline.id}",
        created_at=now,
        updated_at=now,
    )
    session.add(new_task)
    await session.commit()
    await session.refresh(new_task)

    logger.info(
        "pipeline.task_created",
        extra={
            "pipeline_id": str(pipeline.id),
            "source_board_id": str(pipeline.source_board_id),
            "target_board_id": str(pipeline.target_board_id),
            "new_task_id": str(new_task.id),
            "new_task_title": title,
        },
    )
    return new_task
