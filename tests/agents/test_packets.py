import json
from uuid import uuid4

from app.agents.packets import ErrorPacket, FinishPacket, StartPacket, TextDeltaPacket


def test_start_serialises_with_assistant_message_id_and_session_id():
    aid = uuid4()
    sid = uuid4()
    pkt = StartPacket(assistant_message_id=aid, session_id=sid)
    assert json.loads(pkt.model_dump_json()) == {
        "type": "start",
        "assistant_message_id": str(aid),
        "session_id": str(sid),
    }


def test_text_delta_serialises_with_kind_and_step():
    pkt = TextDeltaPacket(delta="hi", step=1)
    assert json.loads(pkt.model_dump_json()) == {
        "type": "text_delta",
        "kind": "text",
        "step": 1,
        "delta": "hi",
    }


def test_text_delta_step_defaults_to_none_before_assigner_runs():
    """Tools / fakes emit step-less; the chat layer's `StepAssigner` fills
    it in before the packet is yielded to the wire."""
    pkt = TextDeltaPacket(delta="hi")
    assert pkt.step is None
    assert pkt.kind == "text"


def test_finish_serialises_with_reason_and_assistant_message_id():
    aid = uuid4()
    pkt = FinishPacket(reason="stop", assistant_message_id=aid)
    assert json.loads(pkt.model_dump_json()) == {
        "type": "finish",
        "reason": "stop",
        "assistant_message_id": str(aid),
    }


def test_error_serialises_with_code_and_message():
    pkt = ErrorPacket(code="agent_failed", message="ProviderTimeout")
    assert json.loads(pkt.model_dump_json()) == {
        "type": "error",
        "code": "agent_failed",
        "message": "ProviderTimeout",
    }
