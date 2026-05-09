from typing import Annotated, Union

from pydantic import Field

from app.agents.packets import ErrorPacket, RunDonePacket, TextDeltaPacket
from app.agents.tools._base import Tool
from app.agents.tools.memory import ManageMemoryTool, SearchMemoriesTool

ALL_TOOL_CLASSES: list[type[Tool]] = [SearchMemoriesTool, ManageMemoryTool]
TOOL_CLASS_BY_NAME: dict[str, type[Tool]] = {cls.NAME: cls for cls in ALL_TOOL_CLASSES}

_tool_packet_classes = tuple(
    pkt for cls in ALL_TOOL_CLASSES for pkt in (cls.START_PACKET, cls.CALL_PACKET, cls.END_PACKET)
)

# Dynamic unpack of registered tool packet classes; Pydantic resolves at runtime
# via TypeAdapter. Adding a new tool only requires appending to ALL_TOOL_CLASSES.
Packet = Annotated[
    Union[TextDeltaPacket, RunDonePacket, ErrorPacket, *_tool_packet_classes],  # ty: ignore[invalid-type-form]
    Field(discriminator="type"),
]

__all__ = [
    "ALL_TOOL_CLASSES",
    "TOOL_CLASS_BY_NAME",
    "Packet",
    "Tool",
]
