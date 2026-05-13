"""Pydantic shapes for the sessions API.

`SessionRead` is the full session row; `SessionListItem` is the compact
sidebar-view subset of the same row. `MessageRead` is the per-message
detail used inside `SessionDetailResponse`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

_MAX_TITLE_CHARS = 200


class SessionCreate(BaseModel):
    title: Annotated[str, Field(max_length=_MAX_TITLE_CHARS)] | None = None


class SessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str | None
    created_at: datetime
    last_message_at: datetime | None


class SessionListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str | None
    created_at: datetime
    last_message_at: datetime | None


class SessionListResponse(BaseModel):
    items: list[SessionListItem]
    next_cursor: str | None


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    role: Literal["user", "assistant"]
    content: str
    tool_activity: dict[str, Any] | None
    parent_message_id: UUID | None
    client_tz: str | None
    created_at: datetime


class SessionDetailResponse(BaseModel):
    id: UUID
    title: str | None
    created_at: datetime
    last_message_at: datetime | None
    messages: list[MessageRead]
    next_cursor: str | None
