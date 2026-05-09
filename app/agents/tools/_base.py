import abc
from typing import Any, ClassVar

from pydantic import BaseModel


class Tool[TArgs: BaseModel, TResult: BaseModel](abc.ABC):
    NAME: ClassVar[str]
    DESCRIPTION: ClassVar[str]
    ARGS_MODEL: ClassVar[type[BaseModel]]
    START_PACKET: ClassVar[type[BaseModel]]
    CALL_PACKET: ClassVar[type[BaseModel]]
    END_PACKET: ClassVar[type[BaseModel]]

    def __init__(self, emitter: Any) -> None:
        self.emitter = emitter

    def tool_definition(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.NAME,
                "description": self.DESCRIPTION,
                "parameters": self.ARGS_MODEL.model_json_schema(),
            },
        }

    def emit_start(self, tool_call_id: str) -> None:
        self.emitter.emit(self.START_PACKET(tool_call_id=tool_call_id))

    def emit_call(self, tool_call_id: str, args: TArgs) -> None:
        self.emitter.emit(self.CALL_PACKET(tool_call_id=tool_call_id, arguments=args))

    def emit_end_ok(self, tool_call_id: str, result: TResult) -> None:
        self.emitter.emit(self.END_PACKET(tool_call_id=tool_call_id, status="ok", result=result))

    def emit_end_error(self, tool_call_id: str, error: str) -> None:
        self.emitter.emit(self.END_PACKET(tool_call_id=tool_call_id, status="error", error=error))

    @abc.abstractmethod
    async def run(self, ctx: Any, tool_call_id: str, args: TArgs) -> TResult:
        """Execute the tool. Implementations must call emit_call before work
        and emit_end_ok / emit_end_error after."""
