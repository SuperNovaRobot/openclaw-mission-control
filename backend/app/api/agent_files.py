"""Agent workspace file viewing and editing endpoints."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import require_admin_auth
from app.core.logging import get_logger
from app.db.session import get_session
from app.models.agents import Agent
from app.models.gateways import Gateway
from app.schemas.agent_files import (
    AgentFileContentResponse,
    AgentFileInfo,
    AgentFileListResponse,
    AgentFileWriteRequest,
)
from app.services.openclaw.agent_files import (
    extract_openclaw_agent_id,
    list_agent_files,
    read_agent_file,
    write_agent_file,
)
from app.services.openclaw.gateway_resolver import gateway_client_config
from app.services.openclaw.gateway_rpc import OpenClawGatewayError

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

    from app.core.auth import AuthContext

router = APIRouter(prefix="/agents/{agent_id}/files", tags=["agents"])
SESSION_DEP = Depends(get_session)
ADMIN_DEP = Depends(require_admin_auth)
logger = get_logger(__name__)

_ALLOWED_EXTENSIONS = {".md", ".json", ".txt", ".yaml", ".yml"}


def _validate_file_path(file_path: str) -> str:
    """Validate and sanitize file path to prevent traversal attacks."""
    if not file_path:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="File path is required.",
        )
    if "\x00" in file_path:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid file path.",
        )
    if os.path.isabs(file_path):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Absolute paths are not allowed.",
        )
    normalized = os.path.normpath(file_path)
    if normalized.startswith("..") or "/.." in normalized:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Path traversal is not allowed.",
        )
    _, ext = os.path.splitext(normalized)
    if ext.lower() not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"File extension {ext!r} is not allowed. Allowed: {', '.join(sorted(_ALLOWED_EXTENSIONS))}",
        )
    return normalized


async def _resolve_agent_and_config(
    agent_id: UUID,
    session: AsyncSession,
) -> tuple[Agent, str, Gateway]:
    """Load agent, extract openclaw agent ID, and resolve gateway config."""
    agent = await session.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found.")
    if not agent.openclaw_session_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Agent has no gateway session binding.",
        )
    openclaw_agent_id = extract_openclaw_agent_id(agent.openclaw_session_id)
    if not openclaw_agent_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Could not extract agent ID from session key.",
        )
    gateway = await session.get(Gateway, agent.gateway_id)
    if gateway is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Agent gateway not found.",
        )
    return agent, openclaw_agent_id, gateway


@router.get("", response_model=AgentFileListResponse)
async def list_files(
    agent_id: UUID,
    session: AsyncSession = SESSION_DEP,
    _auth: AuthContext = ADMIN_DEP,
) -> AgentFileListResponse:
    """List workspace files for an agent."""
    agent, openclaw_agent_id, gateway = await _resolve_agent_and_config(agent_id, session)
    config = gateway_client_config(gateway)
    try:
        raw_files = await list_agent_files(config, openclaw_agent_id)
    except OpenClawGatewayError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Gateway error: {exc}",
        ) from exc

    files: list[AgentFileInfo] = []
    for entry in raw_files:
        if isinstance(entry, dict):
            # Use ``name`` as the canonical path — it is the identifier the
            # gateway's agents.files.get / agents.files.set RPCs expect.
            name = entry.get("name", "")
            files.append(
                AgentFileInfo(
                    name=name,
                    path=name,
                    size=entry.get("size"),
                )
            )
        elif isinstance(entry, str):
            files.append(AgentFileInfo(name=entry, path=entry))
    return AgentFileListResponse(agent_id=openclaw_agent_id, files=files)


@router.get("/{file_path:path}", response_model=AgentFileContentResponse)
async def get_file(
    agent_id: UUID,
    file_path: str,
    session: AsyncSession = SESSION_DEP,
    _auth: AuthContext = ADMIN_DEP,
) -> AgentFileContentResponse:
    """Read a workspace file for an agent."""
    validated_path = _validate_file_path(file_path)
    agent, openclaw_agent_id, gateway = await _resolve_agent_and_config(agent_id, session)
    config = gateway_client_config(gateway)
    try:
        content = await read_agent_file(config, openclaw_agent_id, validated_path)
    except OpenClawGatewayError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Gateway error: {exc}",
        ) from exc

    if content is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")
    return AgentFileContentResponse(
        agent_id=openclaw_agent_id,
        path=validated_path,
        content=content,
    )


@router.put("/{file_path:path}", response_model=AgentFileContentResponse)
async def put_file(
    agent_id: UUID,
    file_path: str,
    payload: AgentFileWriteRequest,
    session: AsyncSession = SESSION_DEP,
    _auth: AuthContext = ADMIN_DEP,
) -> AgentFileContentResponse:
    """Write content to an agent workspace file."""
    validated_path = _validate_file_path(file_path)
    agent, openclaw_agent_id, gateway = await _resolve_agent_and_config(agent_id, session)
    config = gateway_client_config(gateway)
    try:
        await write_agent_file(config, openclaw_agent_id, validated_path, payload.content)
    except OpenClawGatewayError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Gateway error: {exc}",
        ) from exc

    logger.info(
        "agent_files.written",
        extra={
            "agent_id": str(agent_id),
            "openclaw_agent_id": openclaw_agent_id,
            "path": validated_path,
        },
    )
    return AgentFileContentResponse(
        agent_id=openclaw_agent_id,
        path=validated_path,
        content=payload.content,
    )
