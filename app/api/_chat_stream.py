"""Stream-state machinery for the chat SSE endpoint.

Pure stream-shape and generator logic — no FastAPI routes, no HTTPExceptions.
The chat router owns request lifecycle and dependency injection; it builds a
`ChatTurn` and hands it to `stream_turn` (or calls `replay_stream` for a
cached reply). End-of-stream persistence of the assistant row lives here too,
since it depends on the same `StreamState` we accumulate during the stream.
"""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal

import structlog
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app.agents import Packet, run_agent_stream
from app.agents.packets import (
    ErrorPacket,
    RunDonePacket,
    TextDeltaPacket,
    ToolCallPacket,
    ToolEndPacket,
)
from app.models.session import Session
from app.models.user import User
from app.schemas.chat import ChatRequest
from app.services.memory_client import MemoryClient
from app.services.sessions import HistoryTurn, record_assistant_message

log = structlog.get_logger(__name__)


class ToolCallRecord(BaseModel):
    """Persisted per-call shape inside `messages.tool_activity`. Field names
    match the JSONB schema on disk — do not rename without a migration."""

    tool_call_id: str
    tool: str
    arguments: dict[str, Any] | None = None
    status: Literal["ok", "error"] | None = None
    result: dict[str, Any] | None = None
    error: str | None = None


@dataclass(slots=True)
class StreamState:
    """Folds packets into the row that lands in `messages` at end-of-stream."""

    parts: list[str] = field(default_factory=list)
    calls: dict[str, ToolCallRecord] = field(default_factory=dict)
    call_order: list[str] = field(default_factory=list)
    saw_error: bool = False

    def fold(self, packet: Packet) -> None:
        match packet:
            case TextDeltaPacket(delta=delta):
                self.parts.append(delta)
            case ErrorPacket():
                self.saw_error = True
            case ToolCallPacket() as p:
                record = self._record_for(p.tool_call_id, p.tool_name)
                record.arguments = p.arguments.model_dump(mode="json")
            case ToolEndPacket() as p:
                record = self._record_for(p.tool_call_id, p.tool_name)
                record.status = p.status
                record.result = p.result.model_dump(mode="json") if p.result is not None else None
                record.error = p.error
            case _:
                pass

    def _record_for(self, call_id: str, tool: str) -> ToolCallRecord:
        record = self.calls.get(call_id)
        if record is None:
            record = ToolCallRecord(tool_call_id=call_id, tool=tool)
            self.calls[call_id] = record
            self.call_order.append(call_id)
        return record

    def assistant_content(self) -> str:
        return "".join(self.parts)

    def tool_activity(self) -> dict[str, Any] | None:
        if not self.call_order:
            return None
        return {"calls": [self.calls[cid].model_dump(mode="json") for cid in self.call_order]}

    def should_persist(self) -> bool:
        return not self.saw_error and bool(self.parts)


def sse_event(packet: Packet) -> str:
    return f"data: {packet.model_dump_json()}\n\n"


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


async def replay_stream(content: str) -> AsyncIterator[str]:
    """SSE for a cached assistant reply: one text_delta with the full body,
    then run_done. The runtime is not invoked."""
    yield sse_event(TextDeltaPacket(delta=content))
    yield sse_event(RunDonePacket(reason="stop"))


async def stream_turn(turn: ChatTurn) -> AsyncIterator[str]:
    """Run the agent for one turn: yield SSE packets, fold them into a
    `StreamState`, and persist the assistant row at end-of-stream.

    No assistant row is written if an ErrorPacket arrived mid-stream or no
    text was emitted — the user can retry with the same client_message_id
    and the agent will re-run.
    """
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
        state.fold(packet)
        yield sse_event(packet)

    if not state.should_persist():
        log.info(
            "chat.no_assistant_row",
            user_id=str(turn.user.id),
            client_message_id=str(turn.body.client_message_id),
            saw_error=state.saw_error,
            empty_parts=not state.parts,
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
            tool_activity=state.tool_activity(),
        )
    except IntegrityError:
        log.warning(
            "chat.assistant_persist_conflict",
            user_id=str(turn.user.id),
            client_message_id=str(turn.body.client_message_id),
        )
