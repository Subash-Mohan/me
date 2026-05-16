"""Pydantic shapes for the sessions API.

`SessionRead` is the full session row; `SessionListItem` is the compact
sidebar-view subset of the same row. `MessageRead` is the per-message
detail used by `MessagesPageResponse`, the paginated message list returned
by `GET /sessions/{id}/messages`.

`TextEvent` / `ToolEvent` describe one timeline slot inside an assistant
turn. The same models are used in three places: in-memory accumulation
in `StreamState`, the JSONB on-disk shape in `messages.events`, and the
read-side response. One Pydantic source of truth keeps wire / storage /
in-memory aligned.
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


class TextEvent(BaseModel):
    """A single text run inside an assistant turn. `content` is the joined
    body of consecutive `text_delta` packets that shared this step."""

    step: int
    kind: Literal["text"] = "text"
    content: str


class ToolEvent(BaseModel):
    """A single tool call inside an assistant turn. All three lifecycle
    packets (`_start` / `_call` / `_end`) for one `tool_call_id` share this
    step and fold into one record."""

    step: int
    kind: Literal["tool"] = "tool"
    tool_call_id: str
    tool: str
    arguments: dict[str, Any] | None = None
    status: Literal["ok", "error"] | None = None
    result: dict[str, Any] | None = None
    error: str | None = None


Event = Annotated[TextEvent | ToolEvent, Field(discriminator="kind")]


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    role: Literal["user", "assistant"]
    content: str
    events: list[Event] | None
    parent_message_id: UUID | None
    client_tz: str | None
    created_at: datetime


class MessagesPageResponse(BaseModel):
    items: list[MessageRead]
    next_cursor: str | None
