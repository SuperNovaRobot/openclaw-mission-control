"""Session completion monitor — polls agent sessions for TASK_COMPLETE/BLOCKED/QUESTION signals.

Phase 1: Completion Detection
- Scans in_progress tasks with assigned agents
- Polls chat.history for TASK_COMPLETE: / TASK_BLOCKED: / TASK_QUESTION: signals
- Updates task status in DB and dispatches alerts
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.logging import get_logger
from app.core.time import utcnow
from app.models.agents import Agent
from app.models.boards import Board
from app.models.tasks import Task
from app.services.openclaw.db_service import OpenClawDBService
from app.services.openclaw.gateway_dispatch import GatewayDispatchService
from app.services.openclaw.gateway_rpc import (
    GatewayConfig,
    get_chat_history,
    OpenClawGatewayError,
)

logger = get_logger(__name__)

# Signal patterns (case-insensitive)
_RE_COMPLETE = re.compile(r"^TASK[_\s]COMPLETE[:\s]+(.+)", re.IGNORECASE | re.MULTILINE)
_RE_BLOCKED = re.compile(r"^TASK[_\s]BLOCKED[:\s]+(.+)", re.IGNORECASE | re.MULTILINE)
_RE_QUESTION = re.compile(r"^TASK[_\s]QUESTION[:\s]+(.+)", re.IGNORECASE | re.MULTILINE)

# Max messages to scan per session
_SCAN_LIMIT = 10


def _extract_signal(text: str) -> tuple[str, str] | None:
    """Return (signal_type, detail) or None if no signal found."""
    for pattern, kind in (
        (_RE_COMPLETE, "complete"),
        (_RE_BLOCKED, "blocked"),
        (_RE_QUESTION, "question"),
    ):
        m = pattern.search(text)
        if m:
            return kind, m.group(1).strip()[:500]
    return None


class SessionCompletionMonitor(OpenClawDBService):
    """Check agent sessions for task completion signals and update task status."""

    async def scan_active_tasks(
        self,
        *,
        organization_id: UUID,
        notify_session_key: str | None = None,
        gateway_url: str | None = None,
        gateway_token: str | None = None,
    ) -> dict[str, Any]:
        """Scan all in_progress tasks with assigned agents for completion signals.

        Returns a summary dict with counts of tasks checked and actions taken.
        """
        results: dict[str, Any] = {
            "checked": 0,
            "completed": 0,
            "blocked": 0,
            "questions": 0,
            "errors": 0,
            "actions": [],
        }

        # Fetch all in_progress tasks with assigned agents
        stmt = (
            select(Task, Agent, Board)
            .join(Agent, Task.assigned_agent_id == Agent.id)  # type: ignore[arg-type]
            .join(Board, Task.board_id == Board.id)  # type: ignore[arg-type]
            .where(Task.status == "in_progress")
            .where(Task.assigned_agent_id.is_not(None))  # type: ignore[union-attr]
            .where(Board.organization_id == organization_id)
        )
        rows = (await self.session.exec(stmt)).all()  # type: ignore[call-overload]

        if not rows:
            logger.info("session_completion_monitor.no_active_tasks")
            return results

        dispatch = GatewayDispatchService(self.session)

        for task, agent, board in rows:
            if not agent.openclaw_session_id:
                continue

            results["checked"] += 1
            session_key = agent.openclaw_session_id

            # Resolve gateway config for this board
            config = await dispatch.optional_gateway_config_for_board(board)
            if config is None:
                logger.warning(
                    "session_completion_monitor.no_gateway",
                    extra={"board_id": str(board.id), "task_id": str(task.id)},
                )
                continue

            # Override config if explicit gateway params provided
            if gateway_url and gateway_token:
                from app.services.openclaw.gateway_rpc import GatewayConfig as _GWCfg
                config = _GWCfg(url=gateway_url, token=gateway_token)

            try:
                signal = await self._check_session(
                    session_key=session_key,
                    config=config,
                    task_id=task.id,
                    agent_name=agent.name,
                )
            except OpenClawGatewayError as exc:
                logger.warning(
                    "session_completion_monitor.gateway_error",
                    extra={"session_key": session_key, "error": str(exc)},
                )
                results["errors"] += 1
                continue
            except Exception as exc:
                logger.exception(
                    "session_completion_monitor.unexpected_error",
                    extra={"session_key": session_key, "error": str(exc)},
                )
                results["errors"] += 1
                continue

            if signal is None:
                continue

            kind, detail = signal
            action = {
                "task_id": str(task.id),
                "task_title": task.title,
                "agent": agent.name,
                "signal": kind,
                "detail": detail,
            }

            if kind == "complete":
                await self._handle_complete(task, agent, board, detail, dispatch, config)
                results["completed"] += 1
                action["outcome"] = "moved_to_review"
            elif kind == "blocked":
                await self._handle_blocked(task, agent, board, detail, dispatch, config)
                results["blocked"] += 1
                action["outcome"] = "flagged_blocked"
            elif kind == "question":
                await self._handle_question(task, agent, board, detail, dispatch, config)
                results["questions"] += 1
                action["outcome"] = "question_routed"

            results["actions"].append(action)

        await self.session.commit()
        logger.info(
            "session_completion_monitor.scan_complete",
            extra={
                "checked": results["checked"],
                "completed": results["completed"],
                "blocked": results["blocked"],
                "questions": results["questions"],
                "errors": results["errors"],
            },
        )
        return results

    async def _check_session(
        self,
        *,
        session_key: str,
        config: GatewayConfig,
        task_id: UUID,
        agent_name: str,
    ) -> tuple[str, str] | None:
        """Poll a session's recent messages for completion signals."""
        history = await get_chat_history(session_key, config, limit=_SCAN_LIMIT)

        messages: list[Any] = []
        if isinstance(history, dict):
            messages = history.get("messages") or history.get("items") or []
        elif isinstance(history, list):
            messages = history

        # Walk messages from newest to oldest (stop on first signal found)
        for msg in reversed(messages):
            if not isinstance(msg, dict):
                continue
            role = str(msg.get("role", "")).lower()
            if role not in ("assistant", "agent"):
                continue
            content = msg.get("content") or msg.get("text") or ""
            if not isinstance(content, str):
                continue
            signal = _extract_signal(content)
            if signal:
                logger.info(
                    "session_completion_monitor.signal_found",
                    extra={
                        "session_key": session_key,
                        "signal": signal[0],
                        "task_id": str(task_id),
                        "agent": agent_name,
                    },
                )
                return signal
        return None

    async def _handle_complete(
        self,
        task: Task,
        agent: Agent,
        board: Board,
        detail: str,
        dispatch: GatewayDispatchService,
        config: GatewayConfig,
    ) -> None:
        """Move task to review and notify lead agent."""
        task.status = "review"
        task.updated_at = utcnow()
        self.session.add(task)

        # Notify lead agent (main session) about completion
        summary_msg = (
            f"TASK COMPLETE — Review Required\n"
            f"Board: {board.name}\n"
            f"Task: {task.title} (ID: {task.id})\n"
            f"Agent: {agent.name}\n"
            f"Summary: {detail}\n\n"
            f"Task moved to REVIEW. Approve or request changes."
        )
        # Try to notify via board's gateway (lead agent handles review)
        try:
            await dispatch.send_agent_message(
                session_key="main",
                config=config,
                agent_name="Nova (Main)",
                message=summary_msg,
            )
        except OpenClawGatewayError:
            pass  # Non-fatal — task status still updated

        logger.info(
            "session_completion_monitor.task_completed",
            extra={"task_id": str(task.id), "agent": agent.name},
        )

    async def _handle_blocked(
        self,
        task: Task,
        agent: Agent,
        board: Board,
        reason: str,
        dispatch: GatewayDispatchService,
        config: GatewayConfig,
    ) -> None:
        """Flag task as blocked and alert lead agent."""
        # Append blocker to description
        blocker_note = f"\n\n⚠️ BLOCKED [{utcnow().strftime('%Y-%m-%d %H:%M')} UTC]: {reason}"
        task.description = (task.description or "") + blocker_note
        task.updated_at = utcnow()
        self.session.add(task)

        alert_msg = (
            f"🚧 TASK BLOCKED\n"
            f"Board: {board.name}\n"
            f"Task: {task.title} (ID: {task.id})\n"
            f"Agent: {agent.name}\n"
            f"Blocker: {reason}\n\n"
            f"Action needed — please unblock or reassign."
        )
        try:
            await dispatch.send_agent_message(
                session_key="main",
                config=config,
                agent_name="Nova (Main)",
                message=alert_msg,
            )
        except OpenClawGatewayError:
            pass

        logger.info(
            "session_completion_monitor.task_blocked",
            extra={"task_id": str(task.id), "agent": agent.name, "reason": reason},
        )

    async def _handle_question(
        self,
        task: Task,
        agent: Agent,
        board: Board,
        question: str,
        dispatch: GatewayDispatchService,
        config: GatewayConfig,
    ) -> None:
        """Route agent question to lead (main) agent for William."""
        question_msg = (
            f"❓ AGENT QUESTION — Needs Your Input\n"
            f"Board: {board.name}\n"
            f"Task: {task.title} (ID: {task.id})\n"
            f"Agent: {agent.name} asks:\n\n"
            f"{question}\n\n"
            f"Reply to unblock. Task is paused pending your answer."
        )
        try:
            await dispatch.send_agent_message(
                session_key="main",
                config=config,
                agent_name="Nova (Main)",
                message=question_msg,
            )
        except OpenClawGatewayError:
            pass

        logger.info(
            "session_completion_monitor.question_routed",
            extra={"task_id": str(task.id), "agent": agent.name},
        )
