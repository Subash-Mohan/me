"""Runtime smoke tests: drive `run_agent_stream` with a fake OpenAI client.

The real OpenRouter call path is exercised by the eval suite; these tests
verify the framework wiring (delta translation, tool-loop bookkeeping, error
propagation) without hitting the network. Stream framing (`start` / `finish`)
belongs to the chat layer and is asserted in `tests/api/test_chat.py`.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from app.agents.packets import ErrorPacket, TextDeltaPacket
from app.agents.tools.memory import ManageMemoryCallPacket, ManageMemoryEndPacket
from tests._db import reset_db, seed_owner


def _chunk(
    *,
    content: str | None = None,
    tool_calls: list[Any] | None = None,
    finish_reason: str | None = None,
) -> Any:
    delta = SimpleNamespace(content=content, tool_calls=tool_calls)
    choice = SimpleNamespace(delta=delta, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice])


def _tc_delta(
    index: int,
    *,
    id: str | None = None,
    name: str | None = None,
    arguments: str | None = None,
) -> Any:
    fn = SimpleNamespace(name=name, arguments=arguments)
    return SimpleNamespace(index=index, id=id, function=fn)


class _FakeStream:
    def __init__(self, chunks: list[Any]) -> None:
        self._chunks = chunks

    def __enter__(self) -> _FakeStream:
        return self

    def __exit__(self, *args: Any) -> bool:
        return False

    def __iter__(self) -> Any:
        return iter(self._chunks)


class _FakeCompletions:
    def __init__(self, scripted_streams: list[list[Any]]) -> None:
        self._streams = iter(scripted_streams)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> _FakeStream:
        self.calls.append(kwargs)
        return _FakeStream(next(self._streams))


class _FakeChat:
    def __init__(self, completions: _FakeCompletions) -> None:
        self.completions = completions


def _install_fake_openai(monkeypatch: Any, scripted_streams: list[list[Any]]) -> _FakeCompletions:
    from app.agents import runtime as runtime_mod

    completions = _FakeCompletions(scripted_streams)
    chat = _FakeChat(completions)

    class _FakeOpenAI:
        def __init__(self, **_: Any) -> None:
            self.chat = chat

    monkeypatch.setattr(runtime_mod, "OpenAI", _FakeOpenAI)
    return completions


def test_run_agent_stream_emits_text_delta_for_simple_turn(db, monkeypatch) -> None:
    reset_db()
    owner_id = seed_owner("phrase for runtime test")

    from app.models.user import User

    user = db.get(User, owner_id)

    from tests._memory_client_fake import FakeMemoryClient

    fake_client = FakeMemoryClient()

    _install_fake_openai(
        monkeypatch,
        [[_chunk(content="Hello"), _chunk(finish_reason="stop")]],
    )

    from app.agents.runtime import run_agent_stream

    packets = list(
        run_agent_stream(
            "hi",
            db=db,
            memory_client=fake_client,
            user=user,
            now_utc="2026-05-09T16:00:00+00:00",
            client_tz="UTC",
        )
    )

    types = [p.type for p in packets]
    assert types == ["text_delta"]
    assert any(isinstance(p, TextDeltaPacket) and p.delta == "Hello" for p in packets)


def test_run_agent_stream_executes_tool_call_and_emits_lifecycle(db, monkeypatch) -> None:
    """Stream-turn 1 ends with finish_reason='tool_calls' for `manage_memory`;
    runtime must emit start/call/end and then call the model again with the
    tool result message appended."""
    reset_db()
    owner_id = seed_owner("phrase for tool turn test")

    from app.models.user import User

    user = db.get(User, owner_id)

    from tests._memory_client_fake import FakeMemoryClient

    fake_client = FakeMemoryClient()

    # A minimal create payload — manage_memory will execute against the real
    # memory_service and persist a row, which is fine for this smoke test.
    args_json = (
        '{"action":"create","text":"smoke test memory","event_date":"2026-05-09","event_tz":"UTC"}'
    )

    turn1 = [
        _chunk(content="ok "),
        _chunk(
            tool_calls=[
                _tc_delta(0, id="tc1", name="manage_memory", arguments=args_json),
            ]
        ),
        _chunk(finish_reason="tool_calls"),
    ]
    turn2 = [_chunk(content="done"), _chunk(finish_reason="stop")]

    completions = _install_fake_openai(monkeypatch, [turn1, turn2])

    from app.agents.runtime import run_agent_stream

    packets = list(
        run_agent_stream(
            "save it",
            db=db,
            memory_client=fake_client,
            user=user,
            now_utc="2026-05-09T16:00:00+00:00",
            client_tz="UTC",
        )
    )

    types = [p.type for p in packets]
    assert types == [
        "text_delta",
        "manage_memory_start",
        "manage_memory_call",
        "manage_memory_end",
        "text_delta",
    ]
    end = next(p for p in packets if isinstance(p, ManageMemoryEndPacket))
    assert end.status == "ok"
    call = next(p for p in packets if isinstance(p, ManageMemoryCallPacket))
    assert call.arguments.action == "create"

    # Second model call should have received the tool result as a message.
    assert len(completions.calls) == 2
    second_messages = completions.calls[1]["messages"]
    tool_messages = [m for m in second_messages if m.get("role") == "tool"]
    assert len(tool_messages) == 1
    assert tool_messages[0]["tool_call_id"] == "tc1"


def test_run_agent_stream_surfaces_invalid_tool_args_to_model(db, monkeypatch) -> None:
    """When the model emits a `manage_memory(update)` call without a
    `memory_id`, the Pydantic validator rejects it. The runtime must surface
    the validation error as a tool-error result (not crash the stream) so
    the next loop turn lets the model self-correct."""
    reset_db()
    owner_id = seed_owner("phrase for invalid-args recovery test")

    from app.models.user import User

    user = db.get(User, owner_id)

    from tests._memory_client_fake import FakeMemoryClient

    fake_client = FakeMemoryClient()

    # Turn 1: model calls manage_memory(update) without memory_id — invalid.
    bad_args = (
        '{"action":"update","text":"revised","event_date":"2026-05-09","event_tz":"Asia/Kolkata"}'
    )
    turn1 = [
        _chunk(
            tool_calls=[
                _tc_delta(0, id="tc_bad", name="manage_memory", arguments=bad_args),
            ]
        ),
        _chunk(finish_reason="tool_calls"),
    ]
    # Turn 2: after seeing the error, model gives up and replies in text.
    turn2 = [_chunk(content="sorry, let me search first"), _chunk(finish_reason="stop")]

    completions = _install_fake_openai(monkeypatch, [turn1, turn2])

    from app.agents.runtime import run_agent_stream

    packets = list(
        run_agent_stream(
            "update that pizza memory to sushi",
            db=db,
            memory_client=fake_client,
            user=user,
            now_utc="2026-05-09T16:00:00+00:00",
            client_tz="Asia/Kolkata",
        )
    )

    types = [p.type for p in packets]
    # No framework ErrorPacket — the stream stayed healthy.
    assert "error" not in types
    # Start + end (error) for the bad tool call, then the recovery text.
    assert types == ["manage_memory_start", "manage_memory_end", "text_delta"]
    end = next(p for p in packets if isinstance(p, ManageMemoryEndPacket))
    assert end.status == "error"
    assert end.error is not None
    assert "memory_id" in end.error  # validator's error message mentions the missing field

    # The model received the error as a tool message on the second turn.
    assert len(completions.calls) == 2
    second_messages = completions.calls[1]["messages"]
    tool_messages = [m for m in second_messages if m.get("role") == "tool"]
    assert len(tool_messages) == 1
    assert tool_messages[0]["tool_call_id"] == "tc_bad"
    payload = json.loads(tool_messages[0]["content"])
    assert "error" in payload
    assert "memory_id" in payload["error"]


def test_run_agent_stream_surfaces_memory_not_found_to_model(db, monkeypatch) -> None:
    """A `MemoryNotFound` raised by the service must reach the model as a
    tool-error result so the model can recover (e.g. call `search_memories`)
    instead of the stream crashing with `agent_stream_failed`."""
    reset_db()
    owner_id = seed_owner("phrase for not-found recovery test")

    from app.models.user import User

    user = db.get(User, owner_id)

    from tests._memory_client_fake import FakeMemoryClient

    fake_client = FakeMemoryClient()

    # Turn 1: model calls manage_memory(update) with a syntactically valid
    # UUID that does not exist in Postgres.
    missing_id = "4e9d500a-a2ff-11ec-8000-3f6531e61df9"
    args_json = (
        '{"action":"update","memory_id":"'
        + missing_id
        + '","text":"revised","event_tz":"Asia/Kolkata"}'
    )
    turn1 = [
        _chunk(
            tool_calls=[
                _tc_delta(0, id="tc_missing", name="manage_memory", arguments=args_json),
            ]
        ),
        _chunk(finish_reason="tool_calls"),
    ]
    turn2 = [_chunk(content="hm, couldn't find it"), _chunk(finish_reason="stop")]

    completions = _install_fake_openai(monkeypatch, [turn1, turn2])

    from app.agents.runtime import run_agent_stream

    packets = list(
        run_agent_stream(
            "update memory 4e9d…",
            db=db,
            memory_client=fake_client,
            user=user,
            now_utc="2026-05-09T16:00:00+00:00",
            client_tz="Asia/Kolkata",
        )
    )

    types = [p.type for p in packets]
    assert "error" not in types
    # The args were valid, so CALL packet is emitted before END(error).
    assert types == [
        "manage_memory_start",
        "manage_memory_call",
        "manage_memory_end",
        "text_delta",
    ]
    end = next(p for p in packets if isinstance(p, ManageMemoryEndPacket))
    assert end.status == "error"
    assert end.error is not None and "MemoryNotFound" in end.error

    assert len(completions.calls) == 2
    tool_messages = [m for m in completions.calls[1]["messages"] if m.get("role") == "tool"]
    assert len(tool_messages) == 1
    payload = json.loads(tool_messages[0]["content"])
    assert "MemoryNotFound" in payload["error"]


def test_run_agent_stream_emits_error_packet_when_provider_raises(db, monkeypatch) -> None:
    """A raised exception in the streaming layer is caught and surfaced as a
    framework `ErrorPacket(code='agent_failed')`."""
    reset_db()
    owner_id = seed_owner("phrase for runtime error test")

    from app.models.user import User

    user = db.get(User, owner_id)

    from app.agents import runtime as runtime_mod
    from tests._memory_client_fake import FakeMemoryClient

    class _BoomCompletions:
        def create(self, **_: Any) -> Any:
            raise RuntimeError("upstream-boom")

    class _BoomChat:
        completions = _BoomCompletions()

    class _BoomOpenAI:
        def __init__(self, **_: Any) -> None:
            self.chat = _BoomChat()

    monkeypatch.setattr(runtime_mod, "OpenAI", _BoomOpenAI)

    fake_client = FakeMemoryClient()

    packets = list(
        runtime_mod.run_agent_stream(
            "hi",
            db=db,
            memory_client=fake_client,
            user=user,
            now_utc="2026-05-09T16:00:00+00:00",
            client_tz="UTC",
        )
    )

    assert len(packets) == 1
    assert isinstance(packets[0], ErrorPacket)
    assert packets[0].code == "agent_failed"
    assert packets[0].message == "RuntimeError"
