"""Stream-state machinery for the chat SSE endpoint.

Pure stream-shape and generator logic — no FastAPI routes, no HTTPExceptions.
The chat router owns request lifecycle and dependency injection; it builds a
`ChatTurn` and hands it to `stream_turn` (or calls `replay_stream` for a
cached reply). End-of-stream persistence of the assistant row lives here too,
since it depends on the same `StreamState` we accumulate during the stream.

Wire shape:

  * Envelope: `start` → … → `finish` (or stream-close on the error path).
  * Content packets carry `kind` (`"text"` / `"tool"`) and `step` (1-based,
    monotonic per turn). A run of consecutive text deltas shares one step;
    a tool's `_start` / `_call` / `_end` share one step.

Server-side `StreamState` folds the same packets into the timeline that
lands in `messages.events` (JSONB list of `TextEvent` / `ToolEvent`) and
the derived `messages.content` text body. `replay_stream` walks that
timeline back into the same packet shape so the live stream and history
replay share one client-side parser.

Generators yield dicts shaped for `sse_starlette.EventSourceResponse`:
`{"event": <packet type>, "data": <json string>}`.
"""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app.agents import Packet, run_agent_stream
from app.agents.packets import (
    ErrorPacket,
    FinishPacket,
    StartPacket,
    TextDeltaPacket,
    ToolCallPacket,
    ToolEndPacket,
    ToolStartPacket,
)
from app.agents.tools import TOOL_CLASS_BY_NAME
from app.models.message import Message
from app.models.session import Session
from app.models.user import User
from app.schemas.chat import ChatRequest
from app.schemas.sessions import TextEvent, ToolEvent
from app.services.memory_client import MemoryClient
from app.services.sessions import HistoryTurn, record_assistant_message

log = structlog.get_logger(__name__)


class StepAssigner:
    """Hands out 1-based step numbers and tracks block transitions.

    Rules:
      * `text → text`: same step.
      * `text → tool`: new step.
      * Same `tool_call_id`, any lifecycle packet: same step.
      * `tool → text` or `tool → different tool`: new step.

    Envelope packets (`start` / `finish` / `error`) return `None` — they're
    frame markers, not timeline content.
    """

    __slots__ = ("_last_kind", "_next", "_text_step", "_tool_steps")

    def __init__(self) -> None:
        self._next: int = 1
        self._text_step: int | None = None
        self._tool_steps: dict[str, int] = {}
        self._last_kind: str | None = None  # "text" | "tool" | None

    def step_for(self, packet: Packet) -> int | None:
        match packet:
            case TextDeltaPacket():
                if self._last_kind != "text":
                    self._text_step = self._next
                    self._next += 1
                self._last_kind = "text"
                return self._text_step
            case ToolStartPacket() | ToolCallPacket() | ToolEndPacket() as p:
                tool_call_id = p.tool_call_id
                if tool_call_id not in self._tool_steps:
                    self._tool_steps[tool_call_id] = self._next
                    self._next += 1
                    # New tool block invalidates any open text run — next text
                    # delta starts a fresh step.
                    self._text_step = None
                self._last_kind = "tool"
                return self._tool_steps[tool_call_id]
            case _:
                return None


@dataclass(slots=True)
class StreamState:
    """Folds packets into the step-keyed timeline that lands in
    `messages.events` at end-of-stream.

    `events[step]` is created on first sighting and refined as later packets
    for that step arrive (a tool's `_start` opens it; `_call` adds args;
    `_end` adds status/result/error). Text steps accumulate their deltas
    into `content`."""

    events: dict[int, TextEvent | ToolEvent] = field(default_factory=dict)
    saw_error: bool = False

    def fold(self, packet: Packet) -> None:
        match packet:
            case TextDeltaPacket(step=step, delta=delta) if step is not None:
                existing = self.events.get(step)
                if isinstance(existing, TextEvent):
                    existing.content += delta
                else:
                    self.events[step] = TextEvent(step=step, content=delta)
            case ErrorPacket():
                self.saw_error = True
            case ToolStartPacket(step=step, tool_call_id=tcid) as p if step is not None:
                self._tool_record(step, tcid, p.tool_name)
            case ToolCallPacket(step=step, tool_call_id=tcid) as p if step is not None:
                record = self._tool_record(step, tcid, p.tool_name)
                record.arguments = p.arguments.model_dump(mode="json")
            case ToolEndPacket(step=step, tool_call_id=tcid) as p if step is not None:
                record = self._tool_record(step, tcid, p.tool_name)
                record.status = p.status
                record.result = p.result.model_dump(mode="json") if p.result is not None else None
                record.error = p.error
            case _:
                pass

    def _tool_record(self, step: int, tool_call_id: str, tool: str) -> ToolEvent:
        existing = self.events.get(step)
        if isinstance(existing, ToolEvent):
            return existing
        record = ToolEvent(step=step, tool_call_id=tool_call_id, tool=tool)
        self.events[step] = record
        return record

    def events_list(self) -> list[dict[str, Any]] | None:
        """Step-sorted JSON-ready dump for the `events` JSONB column."""
        if not self.events:
            return None
        return [self.events[s].model_dump(mode="json") for s in sorted(self.events)]

    def assistant_content(self) -> str:
        """Derived: all text events joined in step order. Single source of
        truth — `content` and `events` cannot drift."""
        return "".join(
            event.content
            for step in sorted(self.events)
            if isinstance(event := self.events[step], TextEvent)
        )

    def should_persist(self) -> bool:
        return not self.saw_error and bool(self.events)


def _sse(packet: Packet) -> dict[str, str]:
    """Render a packet as a sse-starlette event dict."""
    return {"event": packet.type, "data": packet.model_dump_json()}


@dataclass(slots=True)
class ChatTurn:
    """Per-request inputs needed to run one chat turn end-to-end."""

    db: DbSession
    user: User
    session: Session
    body: ChatRequest
    memory_client: MemoryClient
    history: list[HistoryTurn]
    now_utc: str


async def replay_stream(cached: Message) -> AsyncIterator[dict[str, str]]:
    """Rehydrate a persisted assistant turn into the same packet shape as
    the live stream. Walks `cached.events` in step order and emits the
    matching `text_delta` or tool start/call/end packets, then `finish`."""
    yield _sse(StartPacket(assistant_message_id=cached.id, session_id=cached.session_id))
    for event in cached.events or []:
        if event.get("kind") == "text":
            yield _sse(TextDeltaPacket(step=event["step"], delta=event["content"]))
            continue

        tool_cls = TOOL_CLASS_BY_NAME[event["tool"]]
        tcid = event["tool_call_id"]
        step = event["step"]
        yield _sse(tool_cls.START_PACKET(step=step, tool_call_id=tcid))
        if event.get("arguments") is not None:
            yield _sse(
                tool_cls.CALL_PACKET(
                    step=step,
                    tool_call_id=tcid,
                    arguments=tool_cls.ARGS_MODEL.model_validate(event["arguments"]),
                )
            )
        if event.get("status") is not None:
            yield _sse(
                tool_cls.END_PACKET(
                    step=step,
                    tool_call_id=tcid,
                    status=event["status"],
                    result=event.get("result"),
                    error=event.get("error"),
                )
            )
    yield _sse(FinishPacket(reason="stop", assistant_message_id=cached.id))


async def stream_turn(turn: ChatTurn) -> AsyncIterator[dict[str, str]]:
    """Run the agent for one turn, framed by `start` and `finish` packets.

    The assistant message id is allocated up front and advertised in `start`,
    so the client can stitch streamed text to the row that lands in Postgres
    on completion. Each emitted packet is annotated with a `step` by the
    `StepAssigner` before yield + fold, and `StreamState` accumulates the
    step-keyed timeline that lands in `messages.events`. No assistant row is
    persisted if an `ErrorPacket` arrived mid-stream or no content was
    emitted; the leading `start` is still emitted, and the stream terminates
    without `finish` on the error path."""
    assistant_message_id: UUID = uuid4()
    yield _sse(StartPacket(assistant_message_id=assistant_message_id, session_id=turn.session.id))

    assigner = StepAssigner()
    state = StreamState()
    async for packet in run_agent_stream(
        turn.body.message,
        db=turn.db,
        memory_client=turn.memory_client,
        user=turn.user,
        now_utc=turn.now_utc,
        client_tz=turn.body.client_tz,
        history=turn.history,
    ):
        step = assigner.step_for(packet)
        if step is not None:
            # step_for returns non-None only for these content-bearing types;
            # the match narrows so the attribute assignment is well-typed.
            match packet:
                case TextDeltaPacket() | ToolStartPacket() | ToolCallPacket() | ToolEndPacket():
                    packet.step = step
        state.fold(packet)
        yield _sse(packet)

    if not state.should_persist():
        log.info(
            "chat.no_assistant_row",
            user_id=str(turn.user.id),
            client_message_id=str(turn.body.client_message_id),
            saw_error=state.saw_error,
            empty_events=not state.events,
        )
        return

    try:
        await asyncio.to_thread(
            record_assistant_message,
            turn.db,
            user_id=turn.user.id,
            session=turn.session,
            parent_message_id=turn.body.client_message_id,
            content=state.assistant_content(),
            events=state.events_list(),
            id=assistant_message_id,
        )
    except IntegrityError:
        log.warning(
            "chat.assistant_persist_conflict",
            user_id=str(turn.user.id),
            client_message_id=str(turn.body.client_message_id),
        )
        return

    yield _sse(FinishPacket(reason="stop", assistant_message_id=assistant_message_id))
