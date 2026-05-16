from typing import ClassVar, Literal
from uuid import UUID

from pydantic import BaseModel


class StartPacket(BaseModel):
    """First event of every stream — carries the server-allocated assistant
    message id so the client can stitch streamed text to the row that
    eventually lands in Postgres. Envelope packet: no `kind` / `step`."""

    type: Literal["start"] = "start"
    assistant_message_id: UUID
    session_id: UUID


class TextDeltaPacket(BaseModel):
    """A piece of streamed assistant text. Delta-shaped: carries only the new
    fragment, never the running total. `step` ties consecutive deltas into a
    single text run; the client appends to `events[step].content`."""

    type: Literal["text_delta"] = "text_delta"
    kind: Literal["text"] = "text"
    step: int | None = None
    delta: str


class FinishPacket(BaseModel):
    """Terminal event on a successful run. Carries the same
    `assistant_message_id` as the leading `StartPacket`. Envelope packet."""

    type: Literal["finish"] = "finish"
    reason: str
    assistant_message_id: UUID


class ErrorPacket(BaseModel):
    type: Literal["error"] = "error"
    code: str
    message: str


class ToolStartPacket(BaseModel):
    """Structural base for every `{Name}StartPacket`.

    A tool's start fires when the agent decides to invoke it but before args
    are exchanged. `step` and `tool_call_id` together identify the timeline
    slot all three of the tool's lifecycle packets share."""

    kind: Literal["tool"] = "tool"
    step: int | None = None
    tool_call_id: str
    tool_name: ClassVar[str]


class ToolCallPacket(BaseModel):
    """Structural base for every `{Name}CallPacket`.

    Concrete subclasses narrow `arguments` to their tool's args model and pin
    `type` to a literal. `tool_name` lets the dispatcher identify the emitting
    tool without parsing the type string.
    """

    kind: Literal["tool"] = "tool"
    step: int | None = None
    tool_call_id: str
    arguments: BaseModel
    tool_name: ClassVar[str]


class ToolEndPacket(BaseModel):
    """Structural base for every `{Name}EndPacket`."""

    kind: Literal["tool"] = "tool"
    step: int | None = None
    tool_call_id: str
    status: Literal["ok", "error"]
    result: BaseModel | None = None
    error: str | None = None
    tool_name: ClassVar[str]
