import asyncio
from datetime import date, time
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.agents.context import AgentContext
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


class SearchMemoriesStartPacket(BaseModel):
    type: Literal["search_memories_start"] = "search_memories_start"
    tool_call_id: str


class SearchMemoriesCallPacket(BaseModel):
    type: Literal["search_memories_call"] = "search_memories_call"
    tool_call_id: str
    arguments: SearchMemoriesArgs


class SearchMemoriesEndPacket(BaseModel):
    type: Literal["search_memories_end"] = "search_memories_end"
    tool_call_id: str
    status: Literal["ok", "error"]
    result: SearchMemoriesResult | None = None
    error: str | None = None


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

    async def run(
        self,
        ctx: AgentContext,
        tool_call_id: str,
        args: SearchMemoriesArgs,
    ) -> SearchMemoriesResult:
        self.emit_call(tool_call_id, args)
        try:
            search = await asyncio.to_thread(
                memory_service.search_memories,
                ctx.db,
                ctx.memory_client,
                user_id=ctx.user.id,
                q=args.q,
                limit=args.limit,
            )
        except Exception as exc:
            self.emit_end_error(tool_call_id, type(exc).__name__)
            raise
        result = SearchMemoriesResult(
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
        self.emit_end_ok(tool_call_id, result)
        return result


# ─── manage_memory ─────────────────────────────────────────────────────────


class ManageMemoryArgs(BaseModel):
    action: Literal["create", "update", "delete"]
    memory_id: UUID | None = Field(None, description="Required for update/delete.")
    text: str | None = Field(None, description="Required for create; optional for update.")
    event_date: date | None = None
    event_time: time | None = None
    event_tz: str | None = None
    location_lat: float | None = None
    location_lng: float | None = None
    location_label: str | None = None
    idempotency_id: UUID | None = None  # create only

    @model_validator(mode="after")
    def _per_action_required(self) -> "ManageMemoryArgs":
        if self.action == "create" and (
            self.text is None or self.event_date is None or self.event_tz is None
        ):
            raise ValueError("create requires text, event_date, event_tz")
        if self.action in ("update", "delete") and self.memory_id is None:
            raise ValueError(f"{self.action} requires memory_id")
        return self


class MemoryDetailResult(BaseModel):
    kind: Literal["memory"] = "memory"
    memory: dict  # MemoryDetail.model_dump(mode="json")


class DeletedResult(BaseModel):
    kind: Literal["deleted"] = "deleted"
    memory_id: UUID


ManageMemoryResult = Annotated[MemoryDetailResult | DeletedResult, Field(discriminator="kind")]


class ManageMemoryStartPacket(BaseModel):
    type: Literal["manage_memory_start"] = "manage_memory_start"
    tool_call_id: str


class ManageMemoryCallPacket(BaseModel):
    type: Literal["manage_memory_call"] = "manage_memory_call"
    tool_call_id: str
    arguments: ManageMemoryArgs


class ManageMemoryEndPacket(BaseModel):
    type: Literal["manage_memory_end"] = "manage_memory_end"
    tool_call_id: str
    status: Literal["ok", "error"]
    result: MemoryDetailResult | DeletedResult | None = None
    error: str | None = None


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


class ManageMemoryTool(Tool[ManageMemoryArgs, MemoryDetailResult | DeletedResult]):
    NAME = "manage_memory"
    DESCRIPTION = (
        "Create, update, or delete one of the user's memories. Use `create` to "
        "record a new event, `update` to edit an existing one (find memory_id "
        "via `search_memories` first), or `delete` to remove one. Always pass "
        "event_tz as an IANA TZ string (e.g. 'America/New_York')."
    )
    ARGS_MODEL = ManageMemoryArgs
    START_PACKET = ManageMemoryStartPacket
    CALL_PACKET = ManageMemoryCallPacket
    END_PACKET = ManageMemoryEndPacket

    async def run(
        self,
        ctx: AgentContext,
        tool_call_id: str,
        args: ManageMemoryArgs,
    ) -> MemoryDetailResult | DeletedResult:
        from app.schemas.memory import MemoryDetail

        self.emit_call(tool_call_id, args)
        try:
            if args.action == "create":
                # The model_validator enforces these at runtime; asserts narrow
                # for the type checker.
                assert args.text is not None
                assert args.event_date is not None
                assert args.event_tz is not None
                row = await asyncio.to_thread(
                    memory_service.create_memory,
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
                detail = MemoryDetail.model_validate(row, from_attributes=True)
                result: MemoryDetailResult | DeletedResult = MemoryDetailResult(
                    memory=detail.model_dump(mode="json")
                )
            elif args.action == "update":
                assert args.memory_id is not None
                row = await asyncio.to_thread(
                    memory_service.update_memory,
                    ctx.db,
                    ctx.memory_client,
                    user_id=ctx.user.id,
                    memory_id=args.memory_id,
                    **_unset_unprovided(args),
                )
                detail = MemoryDetail.model_validate(row, from_attributes=True)
                result = MemoryDetailResult(memory=detail.model_dump(mode="json"))
            else:
                assert args.memory_id is not None
                await asyncio.to_thread(
                    memory_service.delete_memory,
                    ctx.db,
                    ctx.memory_client,
                    user_id=ctx.user.id,
                    memory_id=args.memory_id,
                )
                result = DeletedResult(memory_id=args.memory_id)
        except Exception as exc:
            self.emit_end_error(tool_call_id, type(exc).__name__)
            raise
        self.emit_end_ok(tool_call_id, result)
        return result
