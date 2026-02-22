"""Task template CRUD endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import col, or_, select

from app.api.deps import get_board_for_user_read, get_board_for_user_write
from app.core.logging import get_logger
from app.core.time import utcnow
from app.db.session import get_session
from app.models.task_templates import TaskTemplate
from app.models.boards import Board
from app.models.tasks import Task
from app.schemas.task_templates import (
    TaskTemplateCreate,
    TaskTemplateRead,
    TaskTemplateUpdate,
)

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

router = APIRouter(prefix="/boards/{board_id}/templates", tags=["task-templates"])
SESSION_DEP = Depends(get_session)
BOARD_USER_READ_DEP = Depends(get_board_for_user_read)
BOARD_USER_WRITE_DEP = Depends(get_board_for_user_write)
logger = get_logger(__name__)


def _to_template_read(template: TaskTemplate) -> TaskTemplateRead:
    return TaskTemplateRead(
        id=template.id,
        organization_id=template.organization_id,
        board_id=template.board_id,
        name=template.name,
        title_template=template.title_template,
        description_template=template.description_template,
        created_from_task_id=template.created_from_task_id,
        created_at=template.created_at,
        updated_at=template.updated_at,
    )


@router.get("", response_model=list[TaskTemplateRead])
async def list_board_templates(
    board: Board = BOARD_USER_READ_DEP,
    session: AsyncSession = SESSION_DEP,
) -> list[TaskTemplateRead]:
    """List templates for this board plus org-wide templates."""
    query = (
        select(TaskTemplate)
        .where(
            col(TaskTemplate.organization_id) == board.organization_id,
            or_(
                col(TaskTemplate.board_id) == board.id,
                col(TaskTemplate.board_id).is_(None),
            ),
        )
        .order_by(col(TaskTemplate.created_at).desc())
    )
    result = await session.exec(query)
    return [_to_template_read(t) for t in result.all()]


@router.post("", status_code=status.HTTP_201_CREATED, response_model=TaskTemplateRead)
async def create_board_template(
    payload: TaskTemplateCreate,
    board: Board = BOARD_USER_WRITE_DEP,
    session: AsyncSession = SESSION_DEP,
) -> TaskTemplateRead:
    """Create a task template scoped to this board or org-wide."""
    template = TaskTemplate(
        organization_id=board.organization_id,
        board_id=payload.board_id if payload.board_id is not None else board.id,
        name=payload.name,
        title_template=payload.title_template,
        description_template=payload.description_template,
    )
    session.add(template)
    await session.commit()
    await session.refresh(template)
    logger.info(
        "task_template.created",
        extra={"template_id": str(template.id), "board_id": str(board.id)},
    )
    return _to_template_read(template)


@router.patch("/{template_id}", response_model=TaskTemplateRead)
async def update_board_template(
    template_id: UUID,
    payload: TaskTemplateUpdate,
    board: Board = BOARD_USER_WRITE_DEP,
    session: AsyncSession = SESSION_DEP,
) -> TaskTemplateRead:
    """Update an existing task template."""
    template = await session.get(TaskTemplate, template_id)
    if template is None or template.organization_id != board.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found.")

    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(template, key, value)
    template.updated_at = utcnow()
    session.add(template)
    await session.commit()
    await session.refresh(template)
    return _to_template_read(template)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_board_template(
    template_id: UUID,
    board: Board = BOARD_USER_WRITE_DEP,
    session: AsyncSession = SESSION_DEP,
) -> None:
    """Delete a task template."""
    template = await session.get(TaskTemplate, template_id)
    if template is None or template.organization_id != board.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found.")
    await session.delete(template)
    await session.commit()
    logger.info(
        "task_template.deleted",
        extra={"template_id": str(template_id), "board_id": str(board.id)},
    )


@router.post(
    "/from-task/{task_id}",
    status_code=status.HTTP_201_CREATED,
    response_model=TaskTemplateRead,
)
async def save_task_as_template(
    task_id: UUID,
    board: Board = BOARD_USER_WRITE_DEP,
    session: AsyncSession = SESSION_DEP,
) -> TaskTemplateRead:
    """Create a template from an existing task's title and description."""
    task = await session.get(Task, task_id)
    if task is None or task.board_id != board.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")

    template = TaskTemplate(
        organization_id=board.organization_id,
        board_id=board.id,
        name=task.title,
        title_template=task.title,
        description_template=task.description,
        created_from_task_id=task.id,
    )
    session.add(template)
    await session.commit()
    await session.refresh(template)
    logger.info(
        "task_template.created_from_task",
        extra={
            "template_id": str(template.id),
            "task_id": str(task_id),
            "board_id": str(board.id),
        },
    )
    return _to_template_read(template)
