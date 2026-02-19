"""Thin API wrappers for async agent lifecycle operations."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.api.deps import ActorContext, require_admin_or_agent, require_org_admin
from app.core.auth import AuthContext, get_auth_context
from app.core.logging import get_logger
from app.core.time import utcnow
from app.db.session import get_session
from app.models.agents import Agent
from app.models.gateways import Gateway
from app.schemas.agents import (
    AgentCreate,
    AgentHeartbeat,
    AgentHeartbeatCreate,
    AgentRead,
    AgentUpdate,
)
from app.schemas.common import OkResponse
from app.schemas.pagination import DefaultLimitOffsetPage
from app.services.openclaw.gateway_resolver import gateway_client_config
from app.services.openclaw.gateway_rpc import (
    OpenClawGatewayError,
    ensure_session,
    openclaw_call,
    send_message,
)
from app.services.openclaw.provisioning_db import AgentLifecycleService, AgentUpdateOptions
from app.services.organizations import OrganizationContext

if TYPE_CHECKING:
    from fastapi_pagination.limit_offset import LimitOffsetPage
    from sqlmodel.ext.asyncio.session import AsyncSession

logger = get_logger(__name__)
_SESSION_ID_RE = re.compile(r"^agent:([^:]+):.*$")

router = APIRouter(prefix="/agents", tags=["agents"])

BOARD_ID_QUERY = Query(default=None)
GATEWAY_ID_QUERY = Query(default=None)
SINCE_QUERY = Query(default=None)
SESSION_DEP = Depends(get_session)
ORG_ADMIN_DEP = Depends(require_org_admin)
ACTOR_DEP = Depends(require_admin_or_agent)
AUTH_DEP = Depends(get_auth_context)


@dataclass(frozen=True, slots=True)
class _AgentUpdateParams:
    force: bool
    auth: AuthContext
    ctx: OrganizationContext


def _agent_update_params(
    *,
    force: bool = False,
    auth: AuthContext = AUTH_DEP,
    ctx: OrganizationContext = ORG_ADMIN_DEP,
) -> _AgentUpdateParams:
    return _AgentUpdateParams(force=force, auth=auth, ctx=ctx)


AGENT_UPDATE_PARAMS_DEP = Depends(_agent_update_params)


# ---------------------------------------------------------------------------
# Model selector (Pydantic models defined early so routes can reference them)
# ---------------------------------------------------------------------------

class _ModelInfo(BaseModel):
    id: str
    name: str | None = None
    aliases: list[str] = []


class _AvailableModelsResponse(BaseModel):
    models: list[_ModelInfo]


class _SetModelRequest(BaseModel):
    model: str | None = None


class _SetModelResponse(BaseModel):
    ok: bool = True
    model: str | None = None


@router.get("", response_model=DefaultLimitOffsetPage[AgentRead])
async def list_agents(
    board_id: UUID | None = BOARD_ID_QUERY,
    gateway_id: UUID | None = GATEWAY_ID_QUERY,
    session: AsyncSession = SESSION_DEP,
    ctx: OrganizationContext = ORG_ADMIN_DEP,
) -> LimitOffsetPage[AgentRead]:
    """List agents visible to the active organization admin."""
    service = AgentLifecycleService(session)
    return await service.list_agents(
        board_id=board_id,
        gateway_id=gateway_id,
        ctx=ctx,
    )


@router.get("/stream")
async def stream_agents(
    request: Request,
    board_id: UUID | None = BOARD_ID_QUERY,
    since: str | None = SINCE_QUERY,
    session: AsyncSession = SESSION_DEP,
    ctx: OrganizationContext = ORG_ADMIN_DEP,
) -> EventSourceResponse:
    """Stream agent updates as SSE events."""
    service = AgentLifecycleService(session)
    return await service.stream_agents(
        request=request,
        board_id=board_id,
        since=since,
        ctx=ctx,
    )


@router.post("", response_model=AgentRead)
async def create_agent(
    payload: AgentCreate,
    session: AsyncSession = SESSION_DEP,
    actor: ActorContext = ACTOR_DEP,
) -> AgentRead:
    """Create and provision an agent."""
    service = AgentLifecycleService(session)
    return await service.create_agent(payload=payload, actor=actor)


# NOTE: /available-models MUST be before /{agent_id} to avoid path conflict.
@router.get("/available-models", response_model=_AvailableModelsResponse)
async def available_models(
    ctx: OrganizationContext = ORG_ADMIN_DEP,
) -> _AvailableModelsResponse:
    """List configured/usable LLM models from the gateway config."""
    import json
    from pathlib import Path

    # Mounted read-only from host via compose.yml volume bind.
    config_path = Path("/openclaw-config.json")
    if not config_path.exists():
        return _AvailableModelsResponse(models=[])

    try:
        gw_config = json.loads(config_path.read_text())
    except (json.JSONDecodeError, OSError):
        return _AvailableModelsResponse(models=[])

    defaults = gw_config.get("agents", {}).get("defaults", {})
    model_cfg = defaults.get("model", {})
    models_allowlist = defaults.get("models", {})

    models: list[_ModelInfo] = []
    seen: set[str] = set()

    # Primary model
    primary = model_cfg.get("primary", "")
    if isinstance(model_cfg, str):
        primary = model_cfg
    if primary:
        models.append(_ModelInfo(id=primary, name=f"{primary} (primary)"))
        seen.add(primary)

    # Fallback models
    for fb in model_cfg.get("fallbacks", []) if isinstance(model_cfg, dict) else []:
        if fb not in seen:
            models.append(_ModelInfo(id=fb, name=f"{fb} (fallback)"))
            seen.add(fb)

    # Allowlist models
    if isinstance(models_allowlist, dict):
        for model_id, meta in models_allowlist.items():
            if model_id not in seen:
                alias = meta.get("alias", "") if isinstance(meta, dict) else ""
                label = alias if alias else model_id
                models.append(_ModelInfo(id=model_id, name=label))
                seen.add(model_id)

    return _AvailableModelsResponse(models=models)


@router.get("/{agent_id}", response_model=AgentRead)
async def get_agent(
    agent_id: str,
    session: AsyncSession = SESSION_DEP,
    ctx: OrganizationContext = ORG_ADMIN_DEP,
) -> AgentRead:
    """Get a single agent by id."""
    service = AgentLifecycleService(session)
    return await service.get_agent(agent_id=agent_id, ctx=ctx)


@router.patch("/{agent_id}", response_model=AgentRead)
async def update_agent(
    agent_id: str,
    payload: AgentUpdate,
    params: _AgentUpdateParams = AGENT_UPDATE_PARAMS_DEP,
    session: AsyncSession = SESSION_DEP,
) -> AgentRead:
    """Update agent metadata and optionally reprovision."""
    service = AgentLifecycleService(session)
    return await service.update_agent(
        agent_id=agent_id,
        payload=payload,
        options=AgentUpdateOptions(
            force=params.force,
            user=params.auth.user,
            context=params.ctx,
        ),
    )


@router.post("/{agent_id}/heartbeat", response_model=AgentRead)
async def heartbeat_agent(
    agent_id: str,
    payload: AgentHeartbeat,
    session: AsyncSession = SESSION_DEP,
    actor: ActorContext = ACTOR_DEP,
) -> AgentRead:
    """Record a heartbeat for a specific agent."""
    service = AgentLifecycleService(session)
    return await service.heartbeat_agent(agent_id=agent_id, payload=payload, actor=actor)


@router.post("/heartbeat", response_model=AgentRead)
async def heartbeat_or_create_agent(
    payload: AgentHeartbeatCreate,
    session: AsyncSession = SESSION_DEP,
    actor: ActorContext = ACTOR_DEP,
) -> AgentRead:
    """Heartbeat an existing agent or create/provision one if needed."""
    service = AgentLifecycleService(session)
    return await service.heartbeat_or_create_agent(payload=payload, actor=actor)


@router.delete("/{agent_id}", response_model=OkResponse)
async def delete_agent(
    agent_id: str,
    session: AsyncSession = SESSION_DEP,
    ctx: OrganizationContext = ORG_ADMIN_DEP,
) -> OkResponse:
    """Delete an agent and clean related task state."""
    service = AgentLifecycleService(session)
    return await service.delete_agent(agent_id=agent_id, ctx=ctx)


# ---------------------------------------------------------------------------
# Reset & Wake
# ---------------------------------------------------------------------------

class _ResetWakeResponse(BaseModel):
    ok: bool = True
    message: str = "Agent session reset and wake sent."


@router.post("/{agent_id}/reset-and-wake", response_model=_ResetWakeResponse)
async def reset_and_wake_agent(
    agent_id: UUID,
    session: AsyncSession = SESSION_DEP,
    ctx: OrganizationContext = ORG_ADMIN_DEP,
) -> _ResetWakeResponse:
    """Reset an agent's session and send a wake message."""
    agent = await session.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found.")
    if not agent.openclaw_session_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Agent has no gateway session binding.",
        )
    gateway = await session.get(Gateway, agent.gateway_id)
    if gateway is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Agent gateway not found.",
        )
    config = gateway_client_config(gateway)

    # 1. Reset session (ignore error if session doesn't exist yet)
    try:
        await openclaw_call("sessions.reset", {"key": agent.openclaw_session_id}, config=config)
    except OpenClawGatewayError as exc:
        msg = str(exc).lower()
        if not any(m in msg for m in ("not found", "unknown", "no such")):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Gateway error during reset: {exc}",
            ) from exc

    # 2. Ensure session exists
    try:
        await ensure_session(agent.openclaw_session_id, config=config, label=agent.name)
    except OpenClawGatewayError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Gateway error during session ensure: {exc}",
        ) from exc

    # 3. Send wake message
    try:
        await send_message(
            "You have been reset. Read your workspace files (IDENTITY.md, MEMORY.md, SOUL.md, TOOLS.md) and await instructions.",
            session_key=agent.openclaw_session_id,
            config=config,
            deliver=True,
        )
    except OpenClawGatewayError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Gateway error during wake: {exc}",
        ) from exc

    # 4. Update agent status
    agent.status = "online"
    agent.last_seen_at = utcnow()
    session.add(agent)
    await session.commit()

    logger.info(
        "agent.reset_and_wake",
        extra={"agent_id": str(agent_id), "session_key": agent.openclaw_session_id},
    )
    return _ResetWakeResponse()


@router.get("/{agent_id}/model", response_model=_SetModelResponse)
async def get_agent_model(
    agent_id: UUID,
    session: AsyncSession = SESSION_DEP,
    ctx: OrganizationContext = ORG_ADMIN_DEP,
) -> _SetModelResponse:
    """Get the current LLM model override for an agent from the gateway config."""
    import json
    from pathlib import Path

    agent = await session.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found.")
    if not agent.openclaw_session_id:
        return _SetModelResponse(model=None)

    match = _SESSION_ID_RE.match(agent.openclaw_session_id)
    if not match:
        return _SetModelResponse(model=None)
    openclaw_agent_id = match.group(1)

    config_path = Path("/openclaw-config.json")
    if not config_path.exists():
        return _SetModelResponse(model=None)

    try:
        gw_config = json.loads(config_path.read_text())
    except (json.JSONDecodeError, OSError):
        return _SetModelResponse(model=None)

    for entry in gw_config.get("agents", {}).get("list", []):
        if entry.get("id") == openclaw_agent_id:
            return _SetModelResponse(model=entry.get("model"))

    return _SetModelResponse(model=None)


@router.post("/{agent_id}/model", response_model=_SetModelResponse)
async def set_agent_model(
    agent_id: UUID,
    payload: _SetModelRequest,
    session: AsyncSession = SESSION_DEP,
    ctx: OrganizationContext = ORG_ADMIN_DEP,
) -> _SetModelResponse:
    """Change the LLM model for an agent by writing to the gateway config file."""
    import json
    from pathlib import Path

    agent = await session.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found.")
    if not agent.openclaw_session_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Agent has no gateway session binding.",
        )

    # Extract openclaw agent ID from session key
    match = _SESSION_ID_RE.match(agent.openclaw_session_id)
    if not match:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Could not extract agent ID from session key.",
        )
    openclaw_agent_id = match.group(1)

    # Read the gateway config file
    config_path = Path("/openclaw-config.json")
    if not config_path.exists():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Gateway config file not found.",
        )

    try:
        gw_config = json.loads(config_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read gateway config: {exc}",
        ) from exc

    # Find the agent in agents.list and update its model
    agents_list = gw_config.get("agents", {}).get("list", [])
    agent_found = False
    for entry in agents_list:
        if entry.get("id") == openclaw_agent_id:
            if payload.model:
                entry["model"] = payload.model
            else:
                entry.pop("model", None)  # remove override, fall back to default
            agent_found = True
            break

    if not agent_found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{openclaw_agent_id}' not found in gateway config.",
        )

    # Write the updated config back
    try:
        config_path.write_text(json.dumps(gw_config, indent=2) + "\n")
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to write gateway config: {exc}",
        ) from exc

    logger.info(
        "agent.model_changed",
        extra={
            "agent_id": str(agent_id),
            "openclaw_agent_id": openclaw_agent_id,
            "model": payload.model,
        },
    )
    return _SetModelResponse(model=payload.model)
