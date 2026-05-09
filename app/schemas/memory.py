"""Pydantic shapes for the memory API.

`MemoryDetail` is the full row representation; `MemoryCard` is the compact
list-view subset. The route layer maps ORM rows to these via `model_validate`.
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

ExternalStatus = Literal["synced", "unsynced", "pending_delete"]


# Conservative server-side cap on individual journal entries. Pydantic 422 at
# the boundary keeps oversized payloads out of Supermemory's token quota.
_MAX_TEXT_CHARS = 32_000


class MemoryCreate(BaseModel):
    """Request body for `POST /memories`. Only `text`, `event_date`, `event_tz` are required."""

    text: Annotated[str, Field(min_length=1, max_length=_MAX_TEXT_CHARS)]
    event_date: date
    event_tz: Annotated[str, Field(min_length=1)]
    event_time: time | None = None
    location_lat: Annotated[float, Field(ge=-90, le=90)] | None = None
    location_lng: Annotated[float, Field(ge=-180, le=180)] | None = None
    location_label: str | None = None
    idempotency_id: UUID | None = None


class MemoryPatch(BaseModel):
    """Request body for `PATCH /memories/{id}`. All fields optional.

    Field omission means "leave as-is"; `None` means "clear" (where the column
    is nullable). Service-side `_UNSET` sentinel distinguishes the two —
    Pydantic exposes "omitted" via `model_fields_set`.
    """

    text: Annotated[str, Field(min_length=1, max_length=_MAX_TEXT_CHARS)] | None = None
    event_date: date | None = None
    event_tz: Annotated[str, Field(min_length=1)] | None = None
    event_time: time | None = None
    location_lat: Annotated[float, Field(ge=-90, le=90)] | None = None
    location_lng: Annotated[float, Field(ge=-180, le=180)] | None = None
    location_label: str | None = None

    @model_validator(mode="after")
    def _reject_null_for_non_nullable(self) -> MemoryPatch:
        # `text`, `event_date`, `event_tz` are NOT NULL in the DB and have no
        # "clear" semantics. `None` is only meaningful as the omission default.
        for field in ("text", "event_date", "event_tz"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class MemoryDetail(BaseModel):
    """Full row representation."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    text: str
    event_date: date
    event_time: time | None
    event_tz: str
    location_lat: float | None
    location_lng: float | None
    location_label: str | None
    external_id: str | None
    external_status: ExternalStatus
    external_synced_at: datetime | None
    external_error: str | None
    created_at: datetime
    updated_at: datetime


class MemoryCard(BaseModel):
    """Compact list-view representation. `text_preview` is the first ~200 chars."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    event_date: date
    location_label: str | None
    text_preview: str
    external_status: ExternalStatus


class MemoryListResponse(BaseModel):
    items: list[MemoryCard]
    next_cursor: str | None


class SearchHit(BaseModel):
    memory: MemoryCard
    similarity: float | None


class MemorySearchResponse(BaseModel):
    items: list[SearchHit]
    source: Literal["supermemory", "local"]
