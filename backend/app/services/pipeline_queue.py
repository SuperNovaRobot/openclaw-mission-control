"""Task pipeline queue persistence and dispatch helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import async_session_maker
from app.models.tasks import Task
from app.services.queue import QueuedTask, enqueue_task
from app.services.queue import requeue_if_failed as generic_requeue_if_failed
from app.services.task_pipeline import evaluate_pipelines

logger = get_logger(__name__)
TASK_TYPE = "task_pipeline"


def enqueue_pipeline_evaluation(
    task_id: UUID,
    board_id: UUID,
    new_status: str,
) -> bool:
    """Enqueue a pipeline evaluation job to Redis."""
    try:
        queued = QueuedTask(
            task_type=TASK_TYPE,
            payload={
                "task_id": str(task_id),
                "board_id": str(board_id),
                "new_status": new_status,
            },
            created_at=datetime.now(UTC),
            attempts=0,
        )
        enqueue_task(queued, settings.rq_queue_name, redis_url=settings.rq_redis_url)
        logger.info(
            "pipeline.queue.enqueued",
            extra={
                "task_id": str(task_id),
                "board_id": str(board_id),
                "new_status": new_status,
            },
        )
        return True
    except Exception as exc:
        logger.warning(
            "pipeline.queue.enqueue_failed",
            extra={
                "task_id": str(task_id),
                "board_id": str(board_id),
                "error": str(exc),
            },
        )
        return False


def decode_pipeline_task(task: QueuedTask) -> dict[str, Any]:
    """Decode a queued pipeline task payload."""
    if task.task_type != TASK_TYPE:
        raise ValueError(f"Unexpected task_type={task.task_type!r}; expected {TASK_TYPE!r}")
    return task.payload


async def process_pipeline_queue_task(task: QueuedTask) -> None:
    """Process a single pipeline evaluation from the queue."""
    payload = decode_pipeline_task(task)
    task_id = UUID(payload["task_id"])
    new_status = payload["new_status"]

    async with async_session_maker() as session:
        db_task = await session.get(Task, task_id)
        if db_task is None:
            logger.warning(
                "pipeline.queue.task_missing",
                extra={"task_id": str(task_id)},
            )
            return

        created = await evaluate_pipelines(session, db_task, new_status)
        if created:
            logger.info(
                "pipeline.queue.evaluated",
                extra={
                    "task_id": str(task_id),
                    "new_status": new_status,
                    "created_count": len(created),
                },
            )


def requeue_pipeline_task(task: QueuedTask, *, delay_seconds: float = 0) -> bool:
    """Requeue a pipeline task with capped retries."""
    try:
        return generic_requeue_if_failed(
            task,
            settings.rq_queue_name,
            max_retries=settings.rq_dispatch_max_retries,
            redis_url=settings.rq_redis_url,
            delay_seconds=delay_seconds,
        )
    except Exception as exc:
        logger.warning(
            "pipeline.queue.requeue_failed",
            extra={"error": str(exc)},
        )
        return False
