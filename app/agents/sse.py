from typing import Any

from app.agents.packets import TextDeltaPacket
from app.agents.tools._base import Tool


def translate_framework(sdk_event: Any) -> list[Any]:
    """SDK event → framework packets (text_delta only).
    Tool packets are emitted by the tools themselves.

    Only `response.output_text.delta` produces a TextDeltaPacket — other raw
    sub-events (notably `response.function_call_arguments.delta`) also carry a
    `delta` attribute and would otherwise leak tool-argument JSON into the
    user-facing text stream.
    """
    if getattr(sdk_event, "type", None) == "raw_response_event":
        data = getattr(sdk_event, "data", None)
        if getattr(data, "type", None) != "response.output_text.delta":
            return []
        delta = getattr(data, "delta", None)
        if delta:
            return [TextDeltaPacket(delta=str(delta))]
    return []


def _dispatch_tool_start(
    sdk_event: Any,
    tools: dict[str, Tool],
    emitter: Any,  # not used directly; tools hold their own emitter
) -> None:
    """On `tool_called`, ask the right tool to emit its START packet."""
    if (
        getattr(sdk_event, "type", None) == "run_item_stream_event"
        and getattr(sdk_event, "name", None) == "tool_called"
    ):
        item = getattr(sdk_event, "item", None)
        tool_name = getattr(item, "tool_name", None)
        tool_call_id = getattr(item, "tool_call_id", None)
        if tool_name is None or tool_call_id is None:
            return
        tool = tools.get(tool_name)
        if tool is None:
            return
        tool.emit_start(tool_call_id)
