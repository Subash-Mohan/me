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

    @abc.abstractmethod
    def run(self, ctx: Any, tool_call_id: str, args: TArgs) -> TResult:
        """Execute the tool synchronously and return its typed result.

        Start/call/end lifecycle packets are emitted by the runtime around this
        call; implementations are pure compute."""
