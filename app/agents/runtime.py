"""Sync agent runtime.

Drives OpenAI chat-completions streaming and a manual tool-calling loop. Yields
framework `Packet`s as they're produced — text deltas mid-stream, and tool
start/call/end triples between stream turns when the model requests a tool.

The chat layer wraps these into SSE frames and stamps the `step` field; this
file is concerned only with the agent loop itself."""

from __future__ import annotations

import json
import logging
from collections.abc import Generator, Iterator, Sequence
from typing import Any, Final

from openai import OpenAI
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.agents.context import AgentContext
from app.agents.instructions import render_system_prompt
from app.agents.packets import ErrorPacket, TextDeltaPacket
from app.agents.tools import ALL_TOOL_CLASSES, Packet
from app.agents.tools._base import Tool
from app.core.config import get_settings
from app.models.user import User
from app.services._memory_errors import (
    MemoryDuplicate,
    MemoryIdempotencyReused,
    MemoryNotFound,
    MemoryValidationError,
)
from app.services.memory_client import MemoryClient
from app.services.sessions import HistoryTurn

log = logging.getLogger(__name__)

_MAX_TOOL_TURNS: Final[int] = 10

# Errors the model can recover from by retrying with corrected arguments.
# Pydantic ValidationError covers arg-schema misuse (e.g. `manage_memory`
# update without `memory_id`); the typed memory errors cover service-layer
# rejections (missing row, duplicate canonical text, bad TZ, etc.). These
# never crash the stream — they become tool-error results so the next loop
# turn lets the model self-correct.
_MODEL_RECOVERABLE_TOOL_ERRORS: Final = (
    ValidationError,
    MemoryNotFound,
    MemoryDuplicate,
    MemoryValidationError,
    MemoryIdempotencyReused,
)


def _tool_spec(tool: Tool) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.NAME,
            "description": tool.DESCRIPTION,
            "parameters": tool.ARGS_MODEL.model_json_schema(),
        },
    }


def _build_messages(
    user_input: str,
    history: Sequence[HistoryTurn] | None,
    now_utc: str,
    client_tz: str,
) -> list[Any]:
    """Return type is `list[Any]` because the SDK's `messages` parameter is a
    union of role-discriminated TypedDicts we can't construct precisely
    without coupling to internal SDK types."""
    msgs: list[Any] = [
        {
            "role": "system",
            "content": render_system_prompt(now_utc=now_utc, client_tz=client_tz),
        }
    ]
    for turn in history or []:
        msgs.append({"role": turn["role"], "content": turn["content"]})
    msgs.append({"role": "user", "content": user_input})
    return msgs


class _PartialToolCall(BaseModel):
    """Fragments of one tool call, accumulated across stream chunks.

    The OpenAI stream delivers `delta.tool_calls[i]` as partial strings tagged
    by `i`; we fold them into one record per index before dispatching."""

    id: str = ""
    name: str = ""
    args: str = ""


def _fold_tool_call_deltas(
    by_idx: dict[int, _PartialToolCall],
    deltas: Sequence[Any],
) -> None:
    """Merge one chunk's `delta.tool_calls` fragments into the running
    per-index accumulator. The stream sends partial `id`, `name`, and
    (chunked) `arguments` strings tagged by index; each is appended or
    overwritten on the matching `_PartialToolCall`."""
    for tc in deltas:
        entry = by_idx.setdefault(tc.index, _PartialToolCall())
        if tc.id:
            entry.id = tc.id
        fn = tc.function
        if fn is None:
            continue
        if fn.name:
            entry.name = fn.name
        if fn.arguments:
            entry.args += fn.arguments


class _TurnResult(BaseModel):
    """One model turn after streaming completes: the assistant's accumulated
    text, any tool calls it wants to invoke next, and the reason streaming
    stopped (`"stop"`, `"tool_calls"`, `"length"`, …)."""

    text: str = ""
    tool_calls: list[_PartialToolCall] = []
    finish_reason: str | None = None


def _stream_one_turn(
    client: OpenAI,
    model: str,
    messages: list[Any],
    tool_specs: Any,
) -> Generator[Packet, None, _TurnResult]:
    """Stream one chat-completion call to its natural end. Yields a
    `TextDeltaPacket` per content fragment as it arrives; returns the folded
    `_TurnResult` so the caller knows whether to run tools or stop."""
    text_parts: list[str] = []
    tool_calls_by_idx: dict[int, _PartialToolCall] = {}
    finish_reason: str | None = None

    with client.chat.completions.create(
        model=model,
        messages=messages,
        tools=tool_specs,
        stream=True,
    ) as stream:
        for chunk in stream:
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            delta = choice.delta
            if delta.content:
                text_parts.append(delta.content)
                yield TextDeltaPacket(delta=delta.content)
            if delta.tool_calls:
                _fold_tool_call_deltas(tool_calls_by_idx, delta.tool_calls)
            if choice.finish_reason:
                finish_reason = choice.finish_reason

    return _TurnResult(
        text="".join(text_parts),
        tool_calls=list(tool_calls_by_idx.values()),
        finish_reason=finish_reason,
    )


def _assistant_message(turn: _TurnResult) -> dict[str, Any]:
    """Render a `_TurnResult` as the OpenAI SDK's `role:"assistant"` message
    shape, ready to append to the running `messages` list."""
    msg: dict[str, Any] = {"role": "assistant"}
    if turn.text:
        msg["content"] = turn.text
    if turn.tool_calls:
        msg["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.name, "arguments": tc.args},
            }
            for tc in turn.tool_calls
        ]
    return msg


def _surface_tool_error(
    tool: Tool,
    tool_call_id: str,
    messages: list[Any],
    exc: BaseException,
    *,
    start_emitted: bool,
) -> Iterator[Packet]:
    """Convert a model-recoverable exception into a tool-error end packet plus
    a `role:"tool"` message. The model sees the error verbatim on the next
    loop turn and can retry (e.g. call `search_memories` to obtain the
    `memory_id` it forgot)."""
    error_label = f"{type(exc).__name__}: {exc}"
    log.info("agent.tool_error_recovered", extra={"tool": tool.NAME, "error": error_label})
    if not start_emitted:
        yield tool.START_PACKET(tool_call_id=tool_call_id)
    yield tool.END_PACKET(tool_call_id=tool_call_id, status="error", error=error_label)
    messages.append(
        {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": json.dumps({"error": error_label}),
        }
    )


def _run_one_tool(
    tc: _PartialToolCall,
    tools_by_name: dict[str, Tool],
    ctx: AgentContext,
    messages: list[Any],
) -> Iterator[Packet]:
    """Validate args, emit lifecycle packets, execute, append tool result to
    the running message list. Pydantic arg-validation errors and recoverable
    service errors are surfaced as tool-error results so the loop continues;
    other exceptions still propagate so the outer driver can surface a
    framework `ErrorPacket`."""
    tool = tools_by_name[tc.name]
    try:
        args = tool.ARGS_MODEL.model_validate_json(tc.args or "{}")
    except ValidationError as exc:
        yield from _surface_tool_error(tool, tc.id, messages, exc, start_emitted=False)
        return

    yield tool.START_PACKET(tool_call_id=tc.id)
    yield tool.CALL_PACKET(tool_call_id=tc.id, arguments=args)
    try:
        result = tool.run(ctx, tc.id, args)
    except _MODEL_RECOVERABLE_TOOL_ERRORS as exc:
        yield from _surface_tool_error(tool, tc.id, messages, exc, start_emitted=True)
        return
    except Exception as exc:
        yield tool.END_PACKET(
            tool_call_id=tc.id,
            status="error",
            error=type(exc).__name__,
        )
        raise
    yield tool.END_PACKET(tool_call_id=tc.id, status="ok", result=result)
    messages.append(
        {
            "role": "tool",
            "tool_call_id": tc.id,
            "content": result.model_dump_json(),
        }
    )


def run_agent_stream(
    user_input: str,
    db: Session,
    memory_client: MemoryClient,
    user: User,
    *,
    now_utc: str,
    client_tz: str,
    history: Sequence[HistoryTurn] | None = None,
) -> Iterator[Packet]:
    """Drive the chat-completions loop end-to-end.

    Each iteration: stream one model turn (text deltas flow to the wire as
    they arrive), append the assistant's reply to `messages`, then either
    finish (no tool calls) or run the requested tools and loop. Capped at
    `_MAX_TOOL_TURNS` re-entries.

    All exceptions are converted to a terminal `ErrorPacket` so the SSE layer
    always observes a clean generator close."""
    settings = get_settings()
    client = OpenAI(
        api_key=settings.openrouter_api_key.get_secret_value(),
        base_url="https://openrouter.ai/api/v1",
    )
    tools_by_name: dict[str, Tool] = {cls.NAME: cls() for cls in ALL_TOOL_CLASSES}
    tool_specs: Any = [_tool_spec(t) for t in tools_by_name.values()]
    ctx = AgentContext(db=db, memory_client=memory_client, user=user)
    messages = _build_messages(user_input, history, now_utc, client_tz)

    try:
        for _ in range(_MAX_TOOL_TURNS):
            turn = yield from _stream_one_turn(
                client, settings.openrouter_default_model, messages, tool_specs
            )
            messages.append(_assistant_message(turn))

            if turn.finish_reason != "tool_calls" or not turn.tool_calls:
                return

            for tc in turn.tool_calls:
                yield from _run_one_tool(tc, tools_by_name, ctx, messages)

        log.warning("agent.max_turns_exceeded")
        yield ErrorPacket(code="agent_max_turns", message="tool loop exceeded cap")
    except Exception as exc:
        log.exception("agent_stream_failed: %s", type(exc).__name__)
        yield ErrorPacket(code="agent_failed", message=type(exc).__name__)
