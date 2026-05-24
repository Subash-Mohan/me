import re
from datetime import date, time
from typing import Any, ClassVar, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.agents.context import AgentContext
from app.agents.packets import ToolCallPacket, ToolEndPacket, ToolStartPacket
from app.agents.tools._base import Tool
from app.services import memory as memory_service


class SearchMemoriesArgs(BaseModel):
    q: str = Field(description="Free-text search query over the user's memories.")
    limit: int = Field(10, ge=1, le=50)


class SearchHit(BaseModel):
    memory_id: UUID
    event_date: date
    text_preview: str
    similarity: float | None  # None for local-FTS fallback hits


class SearchMemoriesResult(BaseModel):
    source: Literal["supermemory", "local"]
    hits: list[SearchHit]


class SearchMemoriesStartPacket(ToolStartPacket):
    type: Literal["search_memories_start"] = "search_memories_start"
    tool_name: ClassVar[str] = "search_memories"


class SearchMemoriesCallPacket(ToolCallPacket):
    type: Literal["search_memories_call"] = "search_memories_call"
    arguments: SearchMemoriesArgs
    tool_name: ClassVar[str] = "search_memories"


class SearchMemoriesEndPacket(ToolEndPacket):
    type: Literal["search_memories_end"] = "search_memories_end"
    result: SearchMemoriesResult | None = None
    tool_name: ClassVar[str] = "search_memories"


class SearchMemoriesTool(Tool[SearchMemoriesArgs, SearchMemoriesResult]):
    NAME = "search_memories"
    DESCRIPTION = (
        "Search the user's memories by semantic similarity. Returns up to "
        "`limit` (default 10, max 50) hits, each with the memory's id, "
        "text preview, event_date, and similarity score."
    )
    ARGS_MODEL = SearchMemoriesArgs
    START_PACKET = SearchMemoriesStartPacket
    CALL_PACKET = SearchMemoriesCallPacket
    END_PACKET = SearchMemoriesEndPacket

    def run(
        self,
        ctx: AgentContext,
        tool_call_id: str,
        args: SearchMemoriesArgs,
    ) -> SearchMemoriesResult:
        search = memory_service.search_memories(
            ctx.db,
            ctx.memory_client,
            user_id=ctx.user.id,
            q=args.q,
            limit=args.limit,
        )
        return SearchMemoriesResult(
            source=search.source,
            hits=[
                SearchHit(
                    memory_id=memory.id,
                    event_date=memory.event_date,
                    text_preview=memory.text[:300],
                    similarity=similarity,
                )
                for memory, similarity in search.hits
            ],
        )


# ─── manage_memory ─────────────────────────────────────────────────────────


class ManageMemoryArgs(BaseModel):
    action: Literal["create", "update"] = Field(
        description=(
            "create: record a new memory. update: modify an existing one — "
            "call search_memories first to find the memory_id."
        )
    )
    memory_id: UUID | None = Field(None, description="Required for update.")
    text: str | None = Field(
        None,
        description=(
            "Memory body. Required for create; optional for update (omit to leave unchanged)."
        ),
    )
    event_date: date | None = Field(
        None, description="ISO date (YYYY-MM-DD). When the event occurred in event_tz."
    )
    event_time: time | None = Field(
        None,
        description=(
            "ISO time (HH:MM or HH:MM:SS, 24-hour) in event_tz local time. "
            "Omit if the user gave only a date."
        ),
    )
    event_tz: str | None = Field(
        None,
        description=(
            "IANA timezone string, e.g. 'America/New_York'. Never an abbreviation like 'EST'."
        ),
    )
    location_lat: float | None = Field(
        None,
        description=(
            "Latitude in decimal degrees (WGS84), -90 to 90. ONLY set this if "
            "the user explicitly provided numeric coordinates. Never infer "
            "from a place name."
        ),
    )
    location_lng: float | None = Field(
        None,
        description=(
            "Longitude in decimal degrees (WGS84), -180 to 180. ONLY set this "
            "if the user explicitly provided numeric coordinates. Never infer "
            "from a place name."
        ),
    )
    location_label: str | None = Field(
        None,
        description=(
            "Human-readable place name from what the user said, e.g. "
            "'Joe's Pizza, Brooklyn' or 'Central Park'."
        ),
    )
    idempotency_id: UUID | None = Field(
        None,
        description=(
            "create only. Pass the same UUID on retries to dedupe a single "
            "logical create. Omit for a fresh create."
        ),
    )

    @field_validator("event_time", mode="before")
    @classmethod
    def _strip_event_time_tz_suffix(cls, v: Any) -> Any:
        """gpt-4o-mini routinely emits 'HH:MM:SS Z' or 'HH:MM:SS+00:00' for
        event_time despite the prompt forbidding it. Normalize at the schema
        boundary so DB storage + JSON wire format are always naked HH:MM:SS.
        The IANA timezone lives in `event_tz`.
        """
        if isinstance(v, str):
            return re.sub(r"(Z|[+-]\d{2}:?\d{2}(:?\d{2})?)$", "", v)
        if isinstance(v, time):
            return v.replace(tzinfo=None)
        return v

    @model_validator(mode="after")
    def _per_action_required(self) -> "ManageMemoryArgs":
        if self.action == "create" and (
            self.text is None or self.event_date is None or self.event_tz is None
        ):
            raise ValueError("create requires text, event_date, event_tz")
        if self.action == "update" and self.memory_id is None:
            raise ValueError("update requires memory_id")
        return self


class MemoryDetailResult(BaseModel):
    kind: Literal["memory"] = "memory"
    memory: dict  # MemoryDetail.model_dump(mode="json")


class ManageMemoryStartPacket(ToolStartPacket):
    type: Literal["manage_memory_start"] = "manage_memory_start"
    tool_name: ClassVar[str] = "manage_memory"


class ManageMemoryCallPacket(ToolCallPacket):
    type: Literal["manage_memory_call"] = "manage_memory_call"
    arguments: ManageMemoryArgs
    tool_name: ClassVar[str] = "manage_memory"


class ManageMemoryEndPacket(ToolEndPacket):
    type: Literal["manage_memory_end"] = "manage_memory_end"
    result: MemoryDetailResult | None = None
    tool_name: ClassVar[str] = "manage_memory"


def _unset_unprovided(args: ManageMemoryArgs) -> dict:
    """None-from-LLM → service _UNSET sentinel for update."""
    from app.services.memory import _UNSET

    fields = (
        "text",
        "event_date",
        "event_time",
        "event_tz",
        "location_lat",
        "location_lng",
        "location_label",
    )
    out: dict = {}
    for f in fields:
        v = getattr(args, f)
        out[f] = _UNSET if v is None else v
    return out


class ManageMemoryTool(Tool[ManageMemoryArgs, MemoryDetailResult]):
    NAME = "manage_memory"
    DESCRIPTION = (
        "Create or update one of the user's memories. Use `create` to record a "
        "new event, or `update` to edit an existing one (find memory_id via "
        "`search_memories` first). Always pass event_tz as an IANA TZ string "
        "(e.g. 'America/New_York')."
    )
    ARGS_MODEL = ManageMemoryArgs
    START_PACKET = ManageMemoryStartPacket
    CALL_PACKET = ManageMemoryCallPacket
    END_PACKET = ManageMemoryEndPacket

    def run(
        self,
        ctx: AgentContext,
        tool_call_id: str,
        args: ManageMemoryArgs,
    ) -> MemoryDetailResult:
        from app.schemas.memory import MemoryDetail

        if args.action == "create":
            assert args.text is not None
            assert args.event_date is not None
            assert args.event_tz is not None
            row = memory_service.create_memory(
                ctx.db,
                ctx.memory_client,
                user_id=ctx.user.id,
                text=args.text,
                event_date=args.event_date,
                event_tz=args.event_tz,
                event_time=args.event_time,
                location_lat=args.location_lat,
                location_lng=args.location_lng,
                location_label=args.location_label,
                idempotency_id=args.idempotency_id,
            )
        else:
            assert args.memory_id is not None
            row = memory_service.update_memory(
                ctx.db,
                ctx.memory_client,
                user_id=ctx.user.id,
                memory_id=args.memory_id,
                **_unset_unprovided(args),
            )
        detail = MemoryDetail.model_validate(row, from_attributes=True)
        return MemoryDetailResult(memory=detail.model_dump(mode="json"))
