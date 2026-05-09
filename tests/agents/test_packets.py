import json

from app.agents.packets import ErrorPacket, RunDonePacket, TextDeltaPacket


def test_text_delta_serialises_with_type_field():
    pkt = TextDeltaPacket(delta="hi")
    assert json.loads(pkt.model_dump_json()) == {"type": "text_delta", "delta": "hi"}


def test_run_done_serialises_with_reason():
    pkt = RunDonePacket(reason="stop")
    assert json.loads(pkt.model_dump_json()) == {"type": "run_done", "reason": "stop"}


def test_error_serialises_with_code_and_message():
    pkt = ErrorPacket(code="agent_failed", message="ProviderTimeout")
    assert json.loads(pkt.model_dump_json()) == {
        "type": "error",
        "code": "agent_failed",
        "message": "ProviderTimeout",
    }
