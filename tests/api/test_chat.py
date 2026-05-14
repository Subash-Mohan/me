"""POST /chat — persistence, replay-on-dup, error path, history threading.

The agent runtime is monkey-patched to a fake async iterator so these tests
exercise the endpoint's persistence + replay logic without hitting OpenRouter.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.agents.packets import ErrorPacket, RunDonePacket, TextDeltaPacket
from app.agents.tools.memory import (
    ManageMemoryArgs,
    ManageMemoryCallPacket,
    ManageMemoryEndPacket,
    MemoryDetailResult,
)
from app.models.message import Message
from app.models.session import Session as SessionModel
from tests._db import reset_db, seed_owner
from tests._memory import auth_headers, owner_id

PHRASE = "chat-test-phrase-marble-canyon"


@pytest.fixture(autouse=True)
def _reset() -> None:
    reset_db()
    seed_owner(PHRASE)


def _parse_sse(text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for line in text.splitlines():
        if line.startswith("data: "):
            out.append(json.loads(line[len("data: ") :]))
    return out


class _FakeRuntime:
    """Stand-in for `run_agent_stream`. Captures call args and yields a
    pre-built packet script when called.

    Pass `script_factory` to build the script lazily (so each call yields
    fresh packet instances). The captured `kwargs` dict lets tests assert
    that history (and other kwargs) was threaded through correctly.
    """

    def __init__(self, script_factory: Any) -> None:
        self.script_factory = script_factory
        self.calls: list[dict[str, Any]] = []

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append({"args": args, "kwargs": kwargs})

        async def gen() -> Any:
            for packet in self.script_factory():
                yield packet

        return gen()


def _install_fake_runtime(monkeypatch: pytest.MonkeyPatch, fake: _FakeRuntime) -> None:
    import app.api._chat_stream as chat_stream

    monkeypatch.setattr(chat_stream, "run_agent_stream", fake)


def _create_session(client: TestClient, headers: dict[str, str]) -> UUID:
    resp = client.post("/sessions", headers=headers, json={})
    assert resp.status_code == 201
    return UUID(resp.json()["id"])


# ─── happy path ────────────────────────────────────────────────────────────


def test_chat_persists_user_and_assistant_rows(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = auth_headers(client, PHRASE)
    owner = owner_id(client, headers)
    session_id = _create_session(client, headers)
    client_message_id = uuid4()

    fake = _FakeRuntime(
        lambda: [
            TextDeltaPacket(delta="Hello "),
            TextDeltaPacket(delta="world"),
            RunDonePacket(reason="stop"),
        ]
    )
    _install_fake_runtime(monkeypatch, fake)

    resp = client.post(
        "/chat",
        headers=headers,
        json={
            "session_id": str(session_id),
            "client_message_id": str(client_message_id),
            "message": "hi there",
            "client_tz": "America/New_York",
        },
    )
    assert resp.status_code == 200

    db.expire_all()
    user_row = db.get(Message, client_message_id)
    assert user_row is not None
    assert user_row.role == "user"
    assert user_row.content == "hi there"
    assert user_row.user_id == owner
    assert user_row.client_tz == "America/New_York"

    assistant = db.query(Message).filter(Message.parent_message_id == client_message_id).one()
    assert assistant.role == "assistant"
    assert assistant.content == "Hello world"
    assert assistant.tool_activity is None
    assert assistant.user_id == owner


def test_chat_autofills_session_title_from_first_message(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = auth_headers(client, PHRASE)
    session_id = _create_session(client, headers)
    fake = _FakeRuntime(lambda: [TextDeltaPacket(delta="ok"), RunDonePacket(reason="stop")])
    _install_fake_runtime(monkeypatch, fake)

    client.post(
        "/chat",
        headers=headers,
        json={
            "session_id": str(session_id),
            "client_message_id": str(uuid4()),
            "message": "a very long first message that should be truncated for the auto title",
            "client_tz": "UTC",
        },
    )

    db.expire_all()
    s = db.get(SessionModel, session_id)
    assert s is not None
    assert s.title is not None
    assert len(s.title) <= 60
    assert s.title.startswith("a very long first")


def test_chat_records_tool_activity_on_assistant_row(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = auth_headers(client, PHRASE)
    session_id = _create_session(client, headers)
    client_message_id = uuid4()

    fake_args = ManageMemoryArgs(
        action="update",
        memory_id=uuid4(),
    )
    update_result = MemoryDetailResult(memory={"id": "x"})

    def script() -> list[Any]:
        return [
            ManageMemoryCallPacket(tool_call_id="tc1", arguments=fake_args),
            ManageMemoryEndPacket(tool_call_id="tc1", status="ok", result=update_result),
            TextDeltaPacket(delta="done"),
            RunDonePacket(reason="stop"),
        ]

    _install_fake_runtime(monkeypatch, _FakeRuntime(script))

    resp = client.post(
        "/chat",
        headers=headers,
        json={
            "session_id": str(session_id),
            "client_message_id": str(client_message_id),
            "message": "delete it",
        },
    )
    assert resp.status_code == 200

    db.expire_all()
    assistant = db.query(Message).filter(Message.parent_message_id == client_message_id).one()
    assert assistant.tool_activity is not None
    assert "calls" in assistant.tool_activity
    calls = assistant.tool_activity["calls"]
    assert len(calls) == 1
    assert calls[0]["tool_call_id"] == "tc1"
    assert calls[0]["tool"] == "manage_memory"
    assert calls[0]["status"] == "ok"
    assert calls[0]["result"] is not None


# ─── replay ────────────────────────────────────────────────────────────────


def test_chat_replays_cached_assistant_without_invoking_runtime(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = auth_headers(client, PHRASE)
    session_id = _create_session(client, headers)
    client_message_id = uuid4()

    first = _FakeRuntime(
        lambda: [TextDeltaPacket(delta="cached body"), RunDonePacket(reason="stop")]
    )
    _install_fake_runtime(monkeypatch, first)

    body = {
        "session_id": str(session_id),
        "client_message_id": str(client_message_id),
        "message": "trigger",
    }
    r1 = client.post("/chat", headers=headers, json=body)
    assert r1.status_code == 200
    assert len(first.calls) == 1

    second = _FakeRuntime(lambda: [TextDeltaPacket(delta="UNUSED"), RunDonePacket(reason="stop")])
    _install_fake_runtime(monkeypatch, second)

    r2 = client.post("/chat", headers=headers, json=body)
    assert r2.status_code == 200
    assert len(second.calls) == 0  # runtime not invoked on replay

    packets = _parse_sse(r2.text)
    assert [p["type"] for p in packets] == ["text_delta", "run_done"]
    assert packets[0]["delta"] == "cached body"


# ─── error path ────────────────────────────────────────────────────────────


def test_chat_does_not_persist_assistant_when_error_packet_emitted(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = auth_headers(client, PHRASE)
    session_id = _create_session(client, headers)
    client_message_id = uuid4()

    fake = _FakeRuntime(
        lambda: [
            TextDeltaPacket(delta="partial"),
            ErrorPacket(code="agent_failed", message="boom"),
        ]
    )
    _install_fake_runtime(monkeypatch, fake)

    resp = client.post(
        "/chat",
        headers=headers,
        json={
            "session_id": str(session_id),
            "client_message_id": str(client_message_id),
            "message": "fail",
        },
    )
    assert resp.status_code == 200

    db.expire_all()
    user_row = db.get(Message, client_message_id)
    assert user_row is not None  # user message still persisted

    assistant_count = (
        db.query(Message).filter(Message.parent_message_id == client_message_id).count()
    )
    assert assistant_count == 0


# ─── 404 / validation ──────────────────────────────────────────────────────


def test_chat_404_when_session_belongs_to_someone_else(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests._db import seed_extra_user, seed_session

    headers = auth_headers(client, PHRASE)
    other = seed_extra_user("other-phrase-chat-9990")
    foreign = seed_session(user_id=other)

    fake = _FakeRuntime(lambda: [RunDonePacket(reason="stop")])
    _install_fake_runtime(monkeypatch, fake)

    resp = client.post(
        "/chat",
        headers=headers,
        json={
            "session_id": str(foreign),
            "client_message_id": str(uuid4()),
            "message": "nope",
        },
    )
    assert resp.status_code == 404
    assert len(fake.calls) == 0


# ─── history threading ────────────────────────────────────────────────────


def test_chat_passes_session_history_to_runtime(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two prior turns then a third — runtime should receive the first two
    pairs as `history` and the third as `user_input`."""
    headers = auth_headers(client, PHRASE)
    session_id = _create_session(client, headers)

    fake = _FakeRuntime(lambda: [TextDeltaPacket(delta="ok"), RunDonePacket(reason="stop")])
    _install_fake_runtime(monkeypatch, fake)

    base = {"session_id": str(session_id), "client_tz": "UTC"}

    # First turn — no history.
    cm1 = uuid4()
    client.post(
        "/chat",
        headers=headers,
        json={**base, "client_message_id": str(cm1), "message": "first user"},
    )
    assert fake.calls[-1]["kwargs"]["history"] == []

    # Reinstall fake for the second turn so we can assert against fresh state.
    fake2 = _FakeRuntime(lambda: [TextDeltaPacket(delta="ok2"), RunDonePacket(reason="stop")])
    _install_fake_runtime(monkeypatch, fake2)

    cm2 = uuid4()
    client.post(
        "/chat",
        headers=headers,
        json={**base, "client_message_id": str(cm2), "message": "second user"},
    )
    history = fake2.calls[-1]["kwargs"]["history"]
    roles = [h["role"] for h in history]
    contents = [h["content"] for h in history]
    assert roles == ["user", "assistant"]
    assert contents == ["first user", "ok"]
