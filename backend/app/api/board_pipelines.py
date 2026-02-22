"""Board task pipeline CRUD endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import col, select

from app.api.deps import get_board_for_user_read, get_board_for_user_write
from app.core.logging import get_logger
from app.core.time import utcnow
from app.db.session import get_session
from app.models.board_task_pipelines import BoardTaskPipeline
from app.models.boards import Board
from app.schemas.board_task_pipelines import (
    BoardTaskPipelineCreate,
    BoardTaskPipelineRead,
    BoardTaskPipelineUpdate,
)

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

router = APIRouter(prefix="/boards/{board_id}/pipelines", tags=["board-pipelines"])
SESSION_DEP = Depends(get_session)
BOARD_USER_READ_DEP = Depends(get_board_for_user_read)
BOARD_USER_WRITE_DEP = Depends(get_board_for_user_write)
logger = get_logger(__name__)


def _to_pipeline_read(pipeline: BoardTaskPipeline) -> BoardTaskPipelineRead:
    return BoardTaskPipelineRead(
        id=pipeline.id,
        source_board_id=pipeline.source_board_id,
        target_board_id=pipeline.target_board_id,
        trigger_status=pipeline.trigger_status,
        enabled=pipeline.enabled,
        task_title_template=pipeline.task_title_template,
        task_description_template=pipeline.task_description_template,
        target_agent_id=pipeline.target_agent_id,
        transfer_files=pipeline.transfer_files,
        notify_agent=pipeline.notify_agent,
        notification_template=pipeline.notification_template,
        created_at=pipeline.created_at,
        updated_at=pipeline.updated_at,
    )


@router.get("", response_model=list[BoardTaskPipelineRead])
async def list_board_pipelines(
    board: Board = BOARD_USER_READ_DEP,
    session: AsyncSession = SESSION_DEP,
) -> list[BoardTaskPipelineRead]:
    """List task pipelines where this board is the source."""
    query = (
        select(BoardTaskPipeline)
        .where(col(BoardTaskPipeline.source_board_id) == board.id)
        .order_by(col(BoardTaskPipeline.created_at).desc())
    )
    result = await session.exec(query)
    return [_to_pipeline_read(p) for p in result.all()]


@router.post("", status_code=status.HTTP_201_CREATED, response_model=BoardTaskPipelineRead)
async def create_board_pipeline(
    payload: BoardTaskPipelineCreate,
    board: Board = BOARD_USER_WRITE_DEP,
    session: AsyncSession = SESSION_DEP,
) -> BoardTaskPipelineRead:
    """Create a task pipeline from this board to a target board."""
    # Validate target board exists and belongs to same org
    target_board = await Board.objects.by_id(payload.target_board_id).first(session)
    if target_board is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Target board not found.",
        )
    if target_board.organization_id != board.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Target board must belong to the same organization.",
        )

    pipeline = BoardTaskPipeline(
        source_board_id=board.id,
        target_board_id=payload.target_board_id,
        trigger_status=payload.trigger_status,
        enabled=payload.enabled,
        task_title_template=payload.task_title_template,
        task_description_template=payload.task_description_template,
        target_agent_id=payload.target_agent_id,
        transfer_files=payload.transfer_files,
        notify_agent=payload.notify_agent,
        notification_template=payload.notification_template,
    )
    session.add(pipeline)
    await session.commit()
    await session.refresh(pipeline)
    logger.info(
        "pipeline.created",
        extra={
            "pipeline_id": str(pipeline.id),
            "source_board_id": str(board.id),
            "target_board_id": str(payload.target_board_id),
        },
    )
    return _to_pipeline_read(pipeline)


@router.patch("/{pipeline_id}", response_model=BoardTaskPipelineRead)
async def update_board_pipeline(
    pipeline_id: UUID,
    payload: BoardTaskPipelineUpdate,
    board: Board = BOARD_USER_WRITE_DEP,
    session: AsyncSession = SESSION_DEP,
) -> BoardTaskPipelineRead:
    """Update an existing pipeline."""
    pipeline = await session.get(BoardTaskPipeline, pipeline_id)
    if pipeline is None or pipeline.source_board_id != board.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline not found.")

    # If changing target board, validate it
    if payload.target_board_id is not None and payload.target_board_id != pipeline.target_board_id:
        target_board = await Board.objects.by_id(payload.target_board_id).first(session)
        if target_board is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Target board not found.",
            )
        if target_board.organization_id != board.organization_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Target board must belong to the same organization.",
            )

    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(pipeline, key, value)
    pipeline.updated_at = utcnow()
    session.add(pipeline)
    await session.commit()
    await session.refresh(pipeline)
    return _to_pipeline_read(pipeline)


@router.delete("/{pipeline_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_board_pipeline(
    pipeline_id: UUID,
    board: Board = BOARD_USER_WRITE_DEP,
    session: AsyncSession = SESSION_DEP,
) -> None:
    """Delete a pipeline."""
    pipeline = await session.get(BoardTaskPipeline, pipeline_id)
    if pipeline is None or pipeline.source_board_id != board.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline not found.")
    await session.delete(pipeline)
    await session.commit()
    logger.info(
        "pipeline.deleted",
        extra={"pipeline_id": str(pipeline_id), "board_id": str(board.id)},
    )
