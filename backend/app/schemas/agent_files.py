"""Schemas for agent workspace file API payloads."""

from __future__ import annotations

from sqlmodel import SQLModel

from app.schemas.common import NonEmptyStr


class AgentFileInfo(SQLModel):
    """Metadata for a single workspace file."""

    name: str
    path: str
    size: int | None = None


class AgentFileListResponse(SQLModel):
    """Response for listing agent workspace files."""

    agent_id: str
    files: list[AgentFileInfo]


class AgentFileContentResponse(SQLModel):
    """Response for reading a single agent workspace file."""

    agent_id: str
    path: str
    content: str


class AgentFileWriteRequest(SQLModel):
    """Request payload for writing an agent workspace file."""

    content: NonEmptyStr
