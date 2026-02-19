"""Agent workspace file operations via gateway RPC."""

from __future__ import annotations

import re
from typing import Any

from app.core.logging import get_logger
from app.services.openclaw.gateway_rpc import GatewayConfig, openclaw_call

logger = get_logger(__name__)

_SESSION_ID_RE = re.compile(r"^agent:([^:]+):.*$")


def extract_openclaw_agent_id(openclaw_session_id: str) -> str | None:
    """Extract the agent ID from a session key like ``agent:mc-<uuid>:main``."""
    match = _SESSION_ID_RE.match(openclaw_session_id)
    return match.group(1) if match else None


async def list_agent_files(
    config: GatewayConfig,
    openclaw_agent_id: str,
) -> list[dict[str, Any]]:
    """List files in an agent's workspace via gateway RPC."""
    result = await openclaw_call(
        "agents.files.list",
        {"agentId": openclaw_agent_id},
        config=config,
    )
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        return result.get("files", [])
    return []


async def read_agent_file(
    config: GatewayConfig,
    openclaw_agent_id: str,
    name: str,
) -> str | None:
    """Read a single file from an agent's workspace via gateway RPC.

    The gateway may return:
    - A plain string (content directly)
    - ``{"content": "..."}``
    - ``{"file": {"content": "..."}}``
    """
    result = await openclaw_call(
        "agents.files.get",
        {"agentId": openclaw_agent_id, "name": name},
        config=config,
    )
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        content = result.get("content")
        if isinstance(content, str):
            return content
        file_obj = result.get("file")
        if isinstance(file_obj, dict):
            nested = file_obj.get("content")
            if isinstance(nested, str):
                return nested
    return None


async def write_agent_file(
    config: GatewayConfig,
    openclaw_agent_id: str,
    name: str,
    content: str,
) -> bool:
    """Write content to an agent workspace file via gateway RPC."""
    await openclaw_call(
        "agents.files.set",
        {"agentId": openclaw_agent_id, "name": name, "content": content},
        config=config,
    )
    return True
