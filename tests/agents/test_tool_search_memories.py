"""Integration tests for SearchMemoriesTool.

Real Postgres + FakeMemoryClient. The phase-file draft assumed seed_owner /
seed_memory return ORM rows and that SearchResult.hits exposes `.memory` /
`.similarity` attributes — neither is true. seed_owner returns a UUID,
SearchResult.hits is `list[tuple[Memory, float | None]]`, and search_memories
takes user_id/q/limit as keyword-only args. This file is written against the
actual shapes.
"""

from datetime import date
from uuid import UUID

import pytest

from app.agents.context import AgentContext
from app.agents.tools.memory import (
    SearchMemoriesArgs,
    SearchMemoriesResult,
    SearchMemoriesTool,
)
from app.models.user import User
from app.services.memory_client import MemoryClientTransientError
from tests._db import reset_db, seed_memory, seed_owner
from tests._memory_client_fake import FakeMemoryClient


@pytest.fixture
def owner_id() -> UUID:
    reset_db()
    return seed_owner("phrase for agent tool tests")


class _ListEmitter:
    def __init__(self):
        self.packets = []

    def emit(self, packet):
        self.packets.append(packet)


@pytest.mark.asyncio
async def test_search_emits_call_and_end_ok(db, owner_id):
    user = db.get(User, owner_id)
    seed_memory(user_id=owner_id, text_body="had pizza on tuesday", event_date=date(2026, 5, 1))

    fake = FakeMemoryClient()
    # Force local-FTS fallback: an empty supermemory result is *not* a fallback
    # path (search_memories only falls back on MemoryClientError). Make .search
    # raise instead, which the service catches and translates into local FTS.
    fake.fail_next("search", error=MemoryClientTransientError("force fallback"))

    emitter = _ListEmitter()
    tool = SearchMemoriesTool(emitter=emitter)
    ctx = AgentContext(db=db, memory_client=fake, user=user, emitter=emitter)

    result = await tool.run(ctx, "tc_1", SearchMemoriesArgs(q="pizza", limit=10))

    assert isinstance(result, SearchMemoriesResult)
    assert result.source == "local"
    assert [p.type for p in emitter.packets] == [
        "search_memories_start",
        "search_memories_call",
        "search_memories_end",
    ]
    assert emitter.packets[0].tool_call_id == "tc_1"
    assert emitter.packets[-1].status == "ok"
    assert len(emitter.packets[-1].result.hits) >= 1


@pytest.mark.asyncio
async def test_search_emits_end_error_and_reraises_on_failure(db, owner_id, monkeypatch):
    from app.services import memory as memory_service

    user = db.get(User, owner_id)
    fake = FakeMemoryClient()
    emitter = _ListEmitter()
    tool = SearchMemoriesTool(emitter=emitter)
    ctx = AgentContext(db=db, memory_client=fake, user=user, emitter=emitter)

    def boom(*a, **kw):
        raise RuntimeError("synthetic")

    monkeypatch.setattr(memory_service, "search_memories", boom)

    with pytest.raises(RuntimeError, match="synthetic"):
        await tool.run(ctx, "tc_2", SearchMemoriesArgs(q="x"))

    assert emitter.packets[-1].type == "search_memories_end"
    assert emitter.packets[-1].status == "error"
    assert emitter.packets[-1].error == "RuntimeError"
