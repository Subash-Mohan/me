from types import SimpleNamespace

from app.agents.packets import TextDeltaPacket
from app.agents.sse import translate_framework


def test_translate_framework_emits_text_delta_for_response_text_delta_event():
    sdk_event = SimpleNamespace(
        type="raw_response_event",
        data=SimpleNamespace(delta="hello", type="response.output_text.delta"),
    )
    out = translate_framework(sdk_event)
    assert len(out) == 1
    assert isinstance(out[0], TextDeltaPacket)
    assert out[0].delta == "hello"


def test_translate_framework_ignores_non_text_events():
    sdk_event = SimpleNamespace(type="agent_updated_stream_event")
    assert translate_framework(sdk_event) == []


def test_translate_framework_skips_function_call_argument_deltas():
    """Tool-argument deltas also carry a `delta` attribute. They must not leak
    into the text stream."""
    sdk_event = SimpleNamespace(
        type="raw_response_event",
        data=SimpleNamespace(delta='{"q":"', type="response.function_call_arguments.delta"),
    )
    assert translate_framework(sdk_event) == []
