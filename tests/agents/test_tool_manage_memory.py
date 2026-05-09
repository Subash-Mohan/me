"""Integration tests for ManageMemoryTool.

Phase-file draft assumed seed_owner/seed_memory return ORM rows; reality is
UUIDs (same divergence as test_tool_search_memories). Tests adapted to the
actual helper shapes and the keyword-only memory-service signatures.
"""

from datetime import date
from uuid import UUID

import pytest

from app.agents.context import AgentContext
from app.agents.tools.memory import (
    DeletedResult,
    ManageMemoryArgs,
    ManageMemoryTool,
    MemoryDetailResult,
)
from app.models.user import User
from tests._db import reset_db, seed_memory, seed_owner
from tests._memory_client_fake import FakeMemoryClient


@pytest.fixture
def owner_id() -> UUID:
    reset_db()
    return seed_owner("phrase for manage-memory tool tests")


class _ListEmitter:
    def __init__(self):
        self.packets = []

    def emit(self, p):
        self.packets.append(p)


@pytest.mark.asyncio
async def test_create_emits_call_and_end_ok(db, owner_id):
    user = db.get(User, owner_id)
    fake = FakeMemoryClient()
    emitter = _ListEmitter()
    ctx = AgentContext(db=db, memory_client=fake, user=user, emitter=emitter)
    tool = ManageMemoryTool(emitter=emitter)

    args = ManageMemoryArgs(
        action="create",
        text="had pizza tuesday",
        event_date=date(2026, 5, 1),
        event_tz="America/New_York",
    )
    result = await tool.run(ctx, "tc_1", args)

    assert isinstance(result, MemoryDetailResult)
    assert result.kind == "memory"
    assert [p.type for p in emitter.packets] == [
        "manage_memory_call",
        "manage_memory_end",
    ]
    assert emitter.packets[-1].status == "ok"


@pytest.mark.asyncio
async def test_delete_emits_call_and_end_ok(db, owner_id):
    user = db.get(User, owner_id)
    mid = seed_memory(user_id=owner_id, text_body="x", event_date=date(2026, 5, 1))
    fake = FakeMemoryClient()
    emitter = _ListEmitter()
    ctx = AgentContext(db=db, memory_client=fake, user=user, emitter=emitter)
    tool = ManageMemoryTool(emitter=emitter)

    result = await tool.run(ctx, "tc_2", ManageMemoryArgs(action="delete", memory_id=mid))

    assert isinstance(result, DeletedResult)
    assert result.memory_id == mid
    assert emitter.packets[-1].status == "ok"


def test_create_validation_rejects_missing_required_fields():
    with pytest.raises(ValueError, match="create requires"):
        ManageMemoryArgs(action="create")


def test_update_validation_rejects_missing_memory_id():
    with pytest.raises(ValueError, match="update requires memory_id"):
        ManageMemoryArgs(action="update")
