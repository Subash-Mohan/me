"""Integration tests for ManageMemoryTool — pure-compute `run()` returns a
typed result. Lifecycle packets are emitted by the runtime, not the tool."""

from datetime import date
from uuid import UUID

import pytest

from app.agents.context import AgentContext
from app.agents.tools.memory import (
    ManageMemoryArgs,
    ManageMemoryTool,
    MemoryDetailResult,
)
from app.models.user import User
from app.schemas.memory import MemoryAgentView
from tests._db import reset_db, seed_owner
from tests._memory_client_fake import FakeMemoryClient


@pytest.fixture
def owner_id() -> UUID:
    reset_db()
    return seed_owner("phrase for manage-memory tool tests")


def test_create_returns_memory_detail(db, owner_id):
    user = db.get(User, owner_id)
    fake = FakeMemoryClient()
    ctx = AgentContext(db=db, memory_client=fake, user=user)
    tool = ManageMemoryTool()

    args = ManageMemoryArgs(
        action="create",
        text="had pizza tuesday",
        event_date=date(2026, 5, 1),
        event_tz="America/New_York",
    )
    result = tool.run(ctx, "tc_1", args)

    assert isinstance(result, MemoryDetailResult)
    assert result.kind == "memory"
    assert isinstance(result.memory, MemoryAgentView)
    assert result.memory.text == "had pizza tuesday"


def test_result_excludes_supermemory_sync_state(db, owner_id):
    """The result is fed back into the model's context as a `role:"tool"`
    message. Surfacing `external_id` / `external_status` would let the model
    pick Supermemory's `document_id` instead of `Memory.id` on a follow-up
    update — the bug this schema split was introduced to fix."""
    user = db.get(User, owner_id)
    fake = FakeMemoryClient()
    ctx = AgentContext(db=db, memory_client=fake, user=user)
    tool = ManageMemoryTool()

    args = ManageMemoryArgs(
        action="create",
        text="lunch with sam",
        event_date=date(2026, 5, 2),
        event_tz="America/New_York",
    )
    result = tool.run(ctx, "tc_2", args)

    wire = result.model_dump_json()
    for leaked in (
        "external_id",
        "external_status",
        "external_synced_at",
        "external_error",
        "created_at",
        "updated_at",
    ):
        assert leaked not in wire, f"{leaked!r} leaked into agent-visible result"


def test_update_round_trip_uses_local_id(db, owner_id):
    """End-to-end: create returns a `MemoryAgentView` whose `id` is the local
    UUID; using *that* id to update must succeed (and not 404 on the
    Supermemory document_id instead)."""
    user = db.get(User, owner_id)
    fake = FakeMemoryClient()
    ctx = AgentContext(db=db, memory_client=fake, user=user)
    tool = ManageMemoryTool()

    created = tool.run(
        ctx,
        "tc_create",
        ManageMemoryArgs(
            action="create",
            text="original text",
            event_date=date(2026, 5, 3),
            event_tz="America/New_York",
        ),
    )
    local_id = created.memory.id

    updated = tool.run(
        ctx,
        "tc_update",
        ManageMemoryArgs(
            action="update",
            memory_id=local_id,
            text="revised text",
        ),
    )
    assert updated.memory.id == local_id
    assert updated.memory.text == "revised text"


def test_create_validation_rejects_missing_required_fields():
    with pytest.raises(ValueError, match="create requires"):
        ManageMemoryArgs(action="create")


def test_update_validation_rejects_missing_memory_id():
    with pytest.raises(ValueError, match="update requires memory_id"):
        ManageMemoryArgs(action="update")
