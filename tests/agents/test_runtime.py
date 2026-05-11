"""Runtime smoke test: drives run_agent_stream with a fake SDK Runner.

The real OpenRouter / OpenAI Agents SDK call path is exercised manually; this
test verifies the framework wiring (event translation, run_done, sentinel).
"""

from types import SimpleNamespace

import pytest

from tests._db import reset_db, seed_owner


@pytest.mark.asyncio
async def test_run_agent_stream_emits_packets_for_simple_text_turn(db, monkeypatch):
    reset_db()
    owner_id = seed_owner("phrase for runtime test")

    from app.models.user import User

    user = db.get(User, owner_id)

    from tests._memory_client_fake import FakeMemoryClient

    fake_client = FakeMemoryClient()

    from app.agents import runtime
    from app.agents.packets import TextDeltaPacket

    class _FakeStreamed:
        async def stream_events(self):
            yield SimpleNamespace(
                type="raw_response_event",
                data=SimpleNamespace(delta="Hello", type="response.output_text.delta"),
            )

    class _FakeRunner:
        @staticmethod
        def run_streamed(agent, input, context):
            return _FakeStreamed()

    monkeypatch.setattr(runtime, "Runner", _FakeRunner)
    monkeypatch.setattr(
        runtime,
        "build_agent",
        lambda emitter, *, now_utc, client_tz: (object(), {}),
    )

    from app.agents.runtime import run_agent_stream

    packets = []
    async for pkt in run_agent_stream(
        "hi",
        db=db,
        memory_client=fake_client,
        user=user,
        now_utc="2026-05-09T16:00:00+00:00",
        client_tz="UTC",
    ):
        packets.append(pkt)

    types = [p.type for p in packets]
    assert "text_delta" in types
    assert types[-1] == "run_done"
    assert any(isinstance(p, TextDeltaPacket) and p.delta == "Hello" for p in packets)
