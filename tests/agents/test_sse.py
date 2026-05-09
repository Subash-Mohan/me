from types import SimpleNamespace

from app.agents.packets import TextDeltaPacket
from app.agents.sse import _dispatch_tool_start, translate_framework
from app.agents.tools.memory import SearchMemoriesTool


class _ListEmitter:
    def __init__(self):
        self.packets = []

    def emit(self, p):
        self.packets.append(p)


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


def test_dispatch_tool_start_calls_emit_start_for_known_tool():
    emitter = _ListEmitter()
    tools = {"search_memories": SearchMemoriesTool(emitter=emitter)}
    sdk_event = SimpleNamespace(
        type="run_item_stream_event",
        name="tool_called",
        item=SimpleNamespace(tool_name="search_memories", tool_call_id="tc_xyz"),
    )
    _dispatch_tool_start(sdk_event, tools, emitter)
    assert len(emitter.packets) == 1
    assert emitter.packets[0].type == "search_memories_start"
    assert emitter.packets[0].tool_call_id == "tc_xyz"


def test_dispatch_tool_start_ignores_unknown_tool():
    emitter = _ListEmitter()
    tools = {}
    sdk_event = SimpleNamespace(
        type="run_item_stream_event",
        name="tool_called",
        item=SimpleNamespace(tool_name="unknown", tool_call_id="tc_x"),
    )
    _dispatch_tool_start(sdk_event, tools, emitter)
    assert emitter.packets == []


def test_dispatch_tool_start_ignores_non_tool_called_events():
    emitter = _ListEmitter()
    tools = {"search_memories": SearchMemoriesTool(emitter=emitter)}
    sdk_event = SimpleNamespace(
        type="run_item_stream_event",
        name="message_output_created",
    )
    _dispatch_tool_start(sdk_event, tools, emitter)
    assert emitter.packets == []
