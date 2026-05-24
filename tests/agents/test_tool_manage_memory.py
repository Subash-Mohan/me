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
    assert result.memory["text"] == "had pizza tuesday"


def test_create_validation_rejects_missing_required_fields():
    with pytest.raises(ValueError, match="create requires"):
        ManageMemoryArgs(action="create")


def test_update_validation_rejects_missing_memory_id():
    with pytest.raises(ValueError, match="update requires memory_id"):
        ManageMemoryArgs(action="update")
