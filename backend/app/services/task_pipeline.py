"""Task pipeline evaluation and execution service."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlmodel import col, select

from app.core.logging import get_logger
from app.core.time import utcnow
from app.models.agents import Agent
from app.models.board_task_pipelines import BoardTaskPipeline
from app.models.boards import Board
from app.models.gateways import Gateway
from app.models.tasks import Task
from app.services.openclaw.agent_files import (
    extract_openclaw_agent_id,
    list_agent_files,
    read_agent_file,
    write_agent_file,
)
from app.services.openclaw.gateway_resolver import (
    optional_gateway_client_config,
)
from app.services.openclaw.gateway_rpc import (
    GatewayConfig as GatewayClientConfig,
    send_message,
)

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

logger = get_logger(__name__)

_TEMPLATE_VAR_RE = re.compile(r"\{\{(\w+(?:\.\w+)*)\}\}")

# Workspace files to transfer between agents (skip auth/config files).
_TRANSFERABLE_EXTENSIONS = frozenset({".md", ".txt", ".json", ".yaml", ".yml"})
# Skip these workspace management files — they're agent-specific.
_SKIP_FILES = frozenset({
    "BOOTSTRAP.md", "IDENTITY.md", "TOOLS.md", "AGENTS.md",
    "HEARTBEAT.md", "SOUL.md", "USER.md", "MEMORY.md",
})


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
            new_task = await _execute_pipeline(session, pipeline, context, agent)
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
    source_agent: Agent | None,
) -> Task:
    """Render templates, create a downstream task, optionally transfer files and notify."""
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

    # --- File transfer (cross-gateway safe) ---
    transferred_files: list[str] = []
    if pipeline.transfer_files and source_agent:
        try:
            transferred_files = await _transfer_agent_files(
                session, source_agent, pipeline, context,
            )
        except Exception:
            logger.exception(
                "pipeline.file_transfer_failed",
                extra={
                    "pipeline_id": str(pipeline.id),
                    "new_task_id": str(new_task.id),
                },
            )

    # --- Agent notification via chat.send ---
    if pipeline.notify_agent:
        try:
            await _notify_target_agent(
                session, pipeline, new_task, context, transferred_files,
            )
        except Exception:
            logger.exception(
                "pipeline.notify_agent_failed",
                extra={
                    "pipeline_id": str(pipeline.id),
                    "new_task_id": str(new_task.id),
                },
            )

    return new_task


async def _resolve_agent_gateway_config(
    session: AsyncSession,
    agent: Agent,
) -> tuple[GatewayClientConfig, str] | None:
    """Resolve an agent's gateway config and openclaw agent ID.

    Returns (config, openclaw_agent_id) or None if not resolvable.
    """
    gateway = await session.get(Gateway, agent.gateway_id)
    if gateway is None:
        return None
    config = optional_gateway_client_config(gateway)
    if config is None:
        return None
    session_id = agent.openclaw_session_id or ""
    openclaw_id = extract_openclaw_agent_id(session_id)
    if not openclaw_id:
        return None
    return config, openclaw_id


def _is_transferable(filename: str) -> bool:
    """Check if a file should be transferred between agents."""
    if filename in _SKIP_FILES:
        return False
    # Allow memory/ files and output files
    for ext in _TRANSFERABLE_EXTENSIONS:
        if filename.endswith(ext):
            return True
    return False


async def _transfer_agent_files(
    session: AsyncSession,
    source_agent: Agent,
    pipeline: BoardTaskPipeline,
    context: dict[str, str],
) -> list[str]:
    """Read files from source agent workspace and write to target agent workspace.

    Supports cross-gateway transfer (e.g. local → Jetson or Jetson → local).
    Returns list of transferred file names.
    """
    source_resolved = await _resolve_agent_gateway_config(session, source_agent)
    if source_resolved is None:
        logger.warning("pipeline.file_transfer.source_not_resolved")
        return []
    source_config, source_oc_id = source_resolved

    # Resolve target agent
    target_agent: Agent | None = None
    if pipeline.target_agent_id:
        target_agent = await session.get(Agent, pipeline.target_agent_id)
    if target_agent is None:
        # Try to find the lead agent on the target board
        lead_query = select(Agent).where(
            col(Agent.board_id) == pipeline.target_board_id,
            col(Agent.is_board_lead).is_(True),
        )
        lead_result = await session.exec(lead_query)
        target_agent = lead_result.first()

    if target_agent is None:
        logger.warning("pipeline.file_transfer.no_target_agent")
        return []

    target_resolved = await _resolve_agent_gateway_config(session, target_agent)
    if target_resolved is None:
        logger.warning("pipeline.file_transfer.target_not_resolved")
        return []
    target_config, target_oc_id = target_resolved

    # List source agent files
    source_files = await list_agent_files(source_config, source_oc_id)
    transferred: list[str] = []

    for file_entry in source_files:
        name = file_entry.get("name", "") if isinstance(file_entry, dict) else str(file_entry)
        if not name or not _is_transferable(name):
            continue

        try:
            content = await read_agent_file(source_config, source_oc_id, name)
            if content is None:
                continue
            # Write to target under pipeline-inputs/ prefix to avoid conflicts
            target_path = f"pipeline-inputs/{name}"
            await write_agent_file(target_config, target_oc_id, target_path, content)
            transferred.append(name)
            logger.debug(
                "pipeline.file_transferred",
                extra={"file": name, "target_path": target_path},
            )
        except Exception:
            logger.warning(
                "pipeline.file_transfer.single_file_failed",
                extra={"file": name},
                exc_info=True,
            )

    logger.info(
        "pipeline.files_transferred",
        extra={
            "count": len(transferred),
            "files": transferred[:10],
            "source_agent": source_oc_id,
            "target_agent": target_oc_id,
        },
    )
    return transferred


async def _notify_target_agent(
    session: AsyncSession,
    pipeline: BoardTaskPipeline,
    new_task: Task,
    context: dict[str, str],
    transferred_files: list[str],
) -> None:
    """Send a chat message to the target agent's session with instructions."""
    # Resolve target agent
    target_agent: Agent | None = None
    if pipeline.target_agent_id:
        target_agent = await session.get(Agent, pipeline.target_agent_id)
    if target_agent is None:
        lead_query = select(Agent).where(
            col(Agent.board_id) == pipeline.target_board_id,
            col(Agent.is_board_lead).is_(True),
        )
        lead_result = await session.exec(lead_query)
        target_agent = lead_result.first()

    if target_agent is None:
        logger.warning("pipeline.notify.no_target_agent")
        return

    target_resolved = await _resolve_agent_gateway_config(session, target_agent)
    if target_resolved is None:
        logger.warning("pipeline.notify.target_not_resolved")
        return
    target_config, _ = target_resolved

    session_key = target_agent.openclaw_session_id
    if not session_key:
        logger.warning("pipeline.notify.no_session_key")
        return

    # Build notification message
    if pipeline.notification_template:
        message = render_pipeline_template(pipeline.notification_template, context)
    else:
        message = (
            f"New task from pipeline: {new_task.title}\n\n"
            f"Source board: {context.get('source_board.name', 'unknown')}\n"
            f"Source task: {context.get('source_task.title', 'unknown')}\n"
        )
        if new_task.description:
            message += f"\nDescription:\n{new_task.description}\n"

    if transferred_files:
        message += f"\nTransferred files ({len(transferred_files)}):\n"
        for f in transferred_files:
            message += f"  - pipeline-inputs/{f}\n"
        message += "\nCheck your pipeline-inputs/ directory for the source files."

    await send_message(
        message,
        session_key=session_key,
        config=target_config,
        deliver=False,
    )
    logger.info(
        "pipeline.agent_notified",
        extra={
            "target_agent": target_agent.name,
            "session_key": session_key,
        },
    )
