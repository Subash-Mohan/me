from typing import Any

from app.agents.packets import TextDeltaPacket


def translate_framework(sdk_event: Any) -> list[Any]:
    """SDK event → framework packets (text_delta only).

    Tool lifecycle packets (`start` / `call` / `end`) are emitted by the tools
    themselves inside their `run()` methods. Only `response.output_text.delta`
    produces a TextDeltaPacket — other raw sub-events (notably
    `response.function_call_arguments.delta`) also carry a `delta` attribute
    and would otherwise leak tool-argument JSON into the user-facing text
    stream.
    """
    if getattr(sdk_event, "type", None) == "raw_response_event":
        data = getattr(sdk_event, "data", None)
        if getattr(data, "type", None) != "response.output_text.delta":
            return []
        delta = getattr(data, "delta", None)
        if delta:
            return [TextDeltaPacket(delta=str(delta))]
    return []
