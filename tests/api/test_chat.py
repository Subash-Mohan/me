"""POST /chat — persistence, replay-on-dup, error path, history threading,
plus the step/kind/events timeline introduced in phase 2.

The agent runtime is monkey-patched to a fake async iterator so these tests
exercise the endpoint's persistence + replay logic without hitting OpenRouter.
The runtime emits text/tool/error packets only; `start` and `finish` framing
plus `step` assignment are owned by the chat layer and asserted directly here.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.agents.packets import ErrorPacket, TextDeltaPacket
from app.agents.tools.memory import (
    ManageMemoryArgs,
    ManageMemoryCallPacket,
    ManageMemoryEndPacket,
    MemoryDetailResult,
)
from app.models.message import Message
from app.models.session import Session as SessionModel
from app.schemas.memory import MemoryAgentView
from tests._db import reset_db, seed_owner
from tests._memory import auth_headers, owner_id

PHRASE = "chat-test-phrase-marble-canyon"


def _fake_memory_view() -> MemoryAgentView:
    """Minimal valid stub for tests that only care about packet plumbing,
    not the memory content. Real values are produced by the memory service
    in other tests."""
    return MemoryAgentView(
        id=uuid4(),
        text="stub",
        event_date=date(2026, 1, 1),
        event_time=None,
        event_tz="UTC",
        location_lat=None,
        location_lng=None,
        location_label=None,
    )


@pytest.fixture(autouse=True)
def _reset() -> None:
    reset_db()
    seed_owner(PHRASE)


def _parse_sse(text: str) -> list[dict[str, Any]]:
    """Parse an sse-starlette wire response into `[{event, payload}, ...]`.

    sse-starlette frames each packet as `event: <name>\\ndata: <json>\\n\\n`.
    We pair the most recent `event:` line with its following `data:` line."""
    out: list[dict[str, Any]] = []
    current_event: str | None = None
    for line in text.splitlines():
        if line.startswith("event: "):
            current_event = line[len("event: ") :].strip()
        elif line.startswith("data: "):
            payload = json.loads(line[len("data: ") :])
            out.append({"event": current_event, "payload": payload})
            current_event = None
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

        def gen() -> Any:
            yield from self.script_factory()

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
    assert assistant.events == [{"step": 1, "kind": "text", "content": "Hello world"}]
    assert assistant.user_id == owner


def test_chat_stream_frames_start_finish_and_id_matches_persisted_row(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The leading `start` and trailing `finish` carry the same
    `assistant_message_id`, and that id is exactly the row's PK in Postgres."""
    headers = auth_headers(client, PHRASE)
    session_id = _create_session(client, headers)
    client_message_id = uuid4()

    fake = _FakeRuntime(lambda: [TextDeltaPacket(delta="ack")])
    _install_fake_runtime(monkeypatch, fake)

    resp = client.post(
        "/chat",
        headers=headers,
        json={
            "session_id": str(session_id),
            "client_message_id": str(client_message_id),
            "message": "hello",
            "client_tz": "UTC",
        },
    )
    assert resp.status_code == 200

    events = _parse_sse(resp.text)
    types = [e["event"] for e in events]
    assert types == ["start", "text_delta", "finish"]

    start_payload = events[0]["payload"]
    delta_payload = events[1]["payload"]
    finish_payload = events[2]["payload"]
    assert start_payload["session_id"] == str(session_id)
    assert start_payload["assistant_message_id"] == finish_payload["assistant_message_id"]
    # Content packet carries kind + step assigned server-side.
    assert delta_payload["kind"] == "text"
    assert delta_payload["step"] == 1

    db.expire_all()
    assistant = db.query(Message).filter(Message.parent_message_id == client_message_id).one()
    assert str(assistant.id) == start_payload["assistant_message_id"]


def test_chat_steps_increment_across_text_tool_text_interleave(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A turn shaped like `text → tool → text → tool → text` produces five
    persisted events with steps [1..5] and alternating kinds."""
    headers = auth_headers(client, PHRASE)
    session_id = _create_session(client, headers)
    client_message_id = uuid4()

    args1 = ManageMemoryArgs(action="update", memory_id=uuid4())
    args2 = ManageMemoryArgs(action="update", memory_id=uuid4())
    result1 = MemoryDetailResult(memory=_fake_memory_view())
    result2 = MemoryDetailResult(memory=_fake_memory_view())

    def script() -> list[Any]:
        return [
            TextDeltaPacket(delta="thinking "),
            TextDeltaPacket(delta="aloud..."),
            ManageMemoryCallPacket(tool_call_id="tc1", arguments=args1),
            ManageMemoryEndPacket(tool_call_id="tc1", status="ok", result=result1),
            TextDeltaPacket(delta="halfway"),
            ManageMemoryCallPacket(tool_call_id="tc2", arguments=args2),
            ManageMemoryEndPacket(tool_call_id="tc2", status="ok", result=result2),
            TextDeltaPacket(delta="done"),
        ]

    _install_fake_runtime(monkeypatch, _FakeRuntime(script))

    resp = client.post(
        "/chat",
        headers=headers,
        json={
            "session_id": str(session_id),
            "client_message_id": str(client_message_id),
            "message": "go",
        },
    )
    assert resp.status_code == 200

    wire = _parse_sse(resp.text)
    # Drop envelope packets, pull (event, step) tuples for content packets.
    envelope = {"start", "finish"}
    content = [(e["event"], e["payload"].get("step")) for e in wire if e["event"] not in envelope]
    # text(step=1) x2 → mm_call(2) → mm_end(2) → text(3) → mm_call(4) → mm_end(4) → text(5)
    assert content == [
        ("text_delta", 1),
        ("text_delta", 1),
        ("manage_memory_call", 2),
        ("manage_memory_end", 2),
        ("text_delta", 3),
        ("manage_memory_call", 4),
        ("manage_memory_end", 4),
        ("text_delta", 5),
    ]

    db.expire_all()
    assistant = db.query(Message).filter(Message.parent_message_id == client_message_id).one()
    assert assistant.events is not None
    steps = [e["step"] for e in assistant.events]
    kinds = [e["kind"] for e in assistant.events]
    assert steps == [1, 2, 3, 4, 5]
    assert kinds == ["text", "tool", "text", "tool", "text"]
    # content is derived from text events in step order.
    assert assistant.content == "thinking aloud...halfwaydone"


def test_chat_autofills_session_title_from_first_message(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = auth_headers(client, PHRASE)
    session_id = _create_session(client, headers)
    fake = _FakeRuntime(lambda: [TextDeltaPacket(delta="ok")])
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


def test_chat_records_tool_event_on_assistant_row(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = auth_headers(client, PHRASE)
    session_id = _create_session(client, headers)
    client_message_id = uuid4()

    fake_args = ManageMemoryArgs(
        action="update",
        memory_id=uuid4(),
    )
    update_result = MemoryDetailResult(memory=_fake_memory_view())

    def script() -> list[Any]:
        return [
            ManageMemoryCallPacket(tool_call_id="tc1", arguments=fake_args),
            ManageMemoryEndPacket(tool_call_id="tc1", status="ok", result=update_result),
            TextDeltaPacket(delta="done"),
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
    assert assistant.events is not None
    assert len(assistant.events) == 2

    tool_event, text_event = assistant.events
    assert tool_event["kind"] == "tool"
    assert tool_event["step"] == 1
    assert tool_event["tool_call_id"] == "tc1"
    assert tool_event["tool"] == "manage_memory"
    assert tool_event["status"] == "ok"
    assert tool_event["result"] is not None

    assert text_event["kind"] == "text"
    assert text_event["step"] == 2
    assert text_event["content"] == "done"

    # `content` is the joined text in step order.
    assert assistant.content == "done"


# ─── replay parity ─────────────────────────────────────────────────────────


def test_chat_replays_cached_assistant_without_invoking_runtime(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = auth_headers(client, PHRASE)
    session_id = _create_session(client, headers)
    client_message_id = uuid4()

    first = _FakeRuntime(lambda: [TextDeltaPacket(delta="cached body")])
    _install_fake_runtime(monkeypatch, first)

    body = {
        "session_id": str(session_id),
        "client_message_id": str(client_message_id),
        "message": "trigger",
    }
    r1 = client.post("/chat", headers=headers, json=body)
    assert r1.status_code == 200
    assert len(first.calls) == 1

    first_events = _parse_sse(r1.text)
    first_assistant_id = first_events[0]["payload"]["assistant_message_id"]

    second = _FakeRuntime(lambda: [TextDeltaPacket(delta="UNUSED")])
    _install_fake_runtime(monkeypatch, second)

    r2 = client.post("/chat", headers=headers, json=body)
    assert r2.status_code == 200
    assert len(second.calls) == 0  # runtime not invoked on replay

    replay_events = _parse_sse(r2.text)
    assert [e["event"] for e in replay_events] == ["start", "text_delta", "finish"]
    delta_payload = replay_events[1]["payload"]
    assert delta_payload["kind"] == "text"
    assert delta_payload["step"] == 1
    assert delta_payload["delta"] == "cached body"
    # Replay must echo the same assistant_message_id as the original run.
    assert replay_events[0]["payload"]["assistant_message_id"] == first_assistant_id
    assert replay_events[2]["payload"]["assistant_message_id"] == first_assistant_id


def test_chat_replay_re_emits_tool_packets_with_persisted_step(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A cached turn with text + 1 tool + text re-emits the full lifecycle on
    retry — tool packets too — with the persisted `step` and `kind`."""
    headers = auth_headers(client, PHRASE)
    session_id = _create_session(client, headers)
    client_message_id = uuid4()

    fake_args = ManageMemoryArgs(action="update", memory_id=uuid4())
    update_result = MemoryDetailResult(memory=_fake_memory_view())

    def script() -> list[Any]:
        return [
            TextDeltaPacket(delta="checking..."),
            ManageMemoryCallPacket(tool_call_id="tc1", arguments=fake_args),
            ManageMemoryEndPacket(tool_call_id="tc1", status="ok", result=update_result),
            TextDeltaPacket(delta="done"),
        ]

    _install_fake_runtime(monkeypatch, _FakeRuntime(script))

    body = {
        "session_id": str(session_id),
        "client_message_id": str(client_message_id),
        "message": "go",
    }
    r1 = client.post("/chat", headers=headers, json=body)
    assert r1.status_code == 200

    # Second POST hits the replay path; runtime must not be re-invoked.
    blocking_fake = _FakeRuntime(lambda: [TextDeltaPacket(delta="UNUSED")])
    _install_fake_runtime(monkeypatch, blocking_fake)

    r2 = client.post("/chat", headers=headers, json=body)
    assert r2.status_code == 200
    assert len(blocking_fake.calls) == 0

    replay = _parse_sse(r2.text)
    types_and_steps = [(e["event"], e["payload"].get("step")) for e in replay]
    # text(step=1) → manage_memory_start/call/end(step=2) → text(step=3) → finish
    assert types_and_steps == [
        ("start", None),
        ("text_delta", 1),
        ("manage_memory_start", 2),
        ("manage_memory_call", 2),
        ("manage_memory_end", 2),
        ("text_delta", 3),
        ("finish", None),
    ]


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

    events = _parse_sse(resp.text)
    # Stream is `start` → delta → error, with NO trailing `finish` — clients
    # treat a stream-close-without-finish as an aborted turn.
    assert [e["event"] for e in events] == ["start", "text_delta", "error"]

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

    fake = _FakeRuntime(lambda: [TextDeltaPacket(delta="x")])
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

    fake = _FakeRuntime(lambda: [TextDeltaPacket(delta="ok")])
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
    fake2 = _FakeRuntime(lambda: [TextDeltaPacket(delta="ok2")])
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


def test_chat_persists_client_location_when_provided(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = auth_headers(client, PHRASE)
    session_id = _create_session(client, headers)
    cm = uuid4()

    fake = _FakeRuntime(lambda: [TextDeltaPacket(delta="ok")])
    _install_fake_runtime(monkeypatch, fake)

    resp = client.post(
        "/chat",
        headers=headers,
        json={
            "session_id": str(session_id),
            "client_message_id": str(cm),
            "message": "hi from a place",
            "client_tz": "Asia/Kolkata",
            "client_location": {"lat": 12.9716, "lng": 77.5946},
        },
    )
    assert resp.status_code == 200

    db.expire_all()
    user_row = db.get(Message, cm)
    assert user_row is not None
    assert user_row.location_lat == pytest.approx(12.9716)
    assert user_row.location_lng == pytest.approx(77.5946)


def test_chat_user_message_has_null_location_when_omitted(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = auth_headers(client, PHRASE)
    session_id = _create_session(client, headers)
    cm = uuid4()

    fake = _FakeRuntime(lambda: [TextDeltaPacket(delta="ok")])
    _install_fake_runtime(monkeypatch, fake)

    resp = client.post(
        "/chat",
        headers=headers,
        json={
            "session_id": str(session_id),
            "client_message_id": str(cm),
            "message": "no location here",
            "client_tz": "UTC",
        },
    )
    assert resp.status_code == 200

    db.expire_all()
    user_row = db.get(Message, cm)
    assert user_row is not None
    assert user_row.location_lat is None
    assert user_row.location_lng is None
