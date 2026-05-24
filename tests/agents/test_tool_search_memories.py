"""Integration tests for SearchMemoriesTool — pure-compute `run()` returns a
typed result. Lifecycle packets are emitted by the runtime, not the tool."""

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


def test_search_returns_local_hits_when_supermemory_falls_back(db, owner_id):
    user = db.get(User, owner_id)
    seed_memory(user_id=owner_id, text_body="had pizza on tuesday", event_date=date(2026, 5, 1))

    fake = FakeMemoryClient()
    # Force local-FTS fallback: an empty supermemory result is *not* a fallback
    # path (search_memories only falls back on MemoryClientError). Make .search
    # raise instead, which the service catches and translates into local FTS.
    fake.fail_next("search", error=MemoryClientTransientError("force fallback"))

    tool = SearchMemoriesTool()
    ctx = AgentContext(db=db, memory_client=fake, user=user)

    result = tool.run(ctx, "tc_1", SearchMemoriesArgs(q="pizza", limit=10))

    assert isinstance(result, SearchMemoriesResult)
    assert result.source == "local"
    assert len(result.hits) >= 1


def test_search_reraises_on_failure(db, owner_id, monkeypatch):
    from app.services import memory as memory_service

    user = db.get(User, owner_id)
    fake = FakeMemoryClient()
    tool = SearchMemoriesTool()
    ctx = AgentContext(db=db, memory_client=fake, user=user)

    def boom(*a, **kw):
        raise RuntimeError("synthetic")

    monkeypatch.setattr(memory_service, "search_memories", boom)

    with pytest.raises(RuntimeError, match="synthetic"):
        tool.run(ctx, "tc_2", SearchMemoriesArgs(q="x"))
