from typing import Literal

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
