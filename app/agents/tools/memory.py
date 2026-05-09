import asyncio
from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

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
