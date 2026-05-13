from typing import ClassVar, Literal

from pydantic import BaseModel


class TextDeltaPacket(BaseModel):
    type: Literal["text_delta"] = "text_delta"
    delta: str


class RunDonePacket(BaseModel):
    type: Literal["run_done"] = "run_done"
    reason: str


class ErrorPacket(BaseModel):
    type: Literal["error"] = "error"
    code: str
    message: str


class ToolCallPacket(BaseModel):
    """Structural base for every `{Name}CallPacket`.

    Concrete subclasses narrow `arguments` to their tool's args model and pin
    `type` to a literal. `tool_name` lets the dispatcher identify the emitting
    tool without parsing the type string.
    """

    tool_call_id: str
    arguments: BaseModel
    tool_name: ClassVar[str]


class ToolEndPacket(BaseModel):
    """Structural base for every `{Name}EndPacket`."""

    tool_call_id: str
    status: Literal["ok", "error"]
    result: BaseModel | None = None
    error: str | None = None
    tool_name: ClassVar[str]
