from typing import Any, Literal

import pytest
from pydantic import BaseModel

from app.agents.tools._base import Tool


class _FakeArgs(BaseModel):
    q: str


class _FakeResult(BaseModel):
    n: int


class _StartPkt(BaseModel):
    type: Literal["fake_start"] = "fake_start"
    tool_call_id: str


class _CallPkt(BaseModel):
    type: Literal["fake_call"] = "fake_call"
    tool_call_id: str
    arguments: _FakeArgs


class _EndPkt(BaseModel):
    type: Literal["fake_end"] = "fake_end"
    tool_call_id: str
    status: Literal["ok", "error"]
    result: _FakeResult | None = None
    error: str | None = None


class _FakeTool(Tool[_FakeArgs, _FakeResult]):
    NAME = "fake"
    DESCRIPTION = "fake"
    ARGS_MODEL = _FakeArgs
    START_PACKET = _StartPkt
    CALL_PACKET = _CallPkt
    END_PACKET = _EndPkt

    async def run(self, ctx, tool_call_id, args):  # type: ignore[override]
        self.emit_call(tool_call_id, args)
        result = _FakeResult(n=len(args.q))
        self.emit_end_ok(tool_call_id, result)
        return result


class _ListEmitter:
    def __init__(self):
        self.packets: list[Any] = []

    def emit(self, packet):
        self.packets.append(packet)


def test_tool_definition_uses_args_schema():
    tool = _FakeTool(emitter=_ListEmitter())
    defn = tool.tool_definition()
    assert defn["type"] == "function"
    assert defn["function"]["name"] == "fake"
    assert defn["function"]["description"] == "fake"
    assert "q" in defn["function"]["parameters"]["properties"]


def test_emit_start_pushes_start_packet():
    emitter = _ListEmitter()
    tool = _FakeTool(emitter=emitter)
    tool.emit_start("tc_1")
    assert len(emitter.packets) == 1
    assert emitter.packets[0].type == "fake_start"
    assert emitter.packets[0].tool_call_id == "tc_1"


@pytest.mark.asyncio
async def test_run_emits_call_then_end_ok():
    emitter = _ListEmitter()
    tool = _FakeTool(emitter=emitter)
    result = await tool.run(ctx=None, tool_call_id="tc_2", args=_FakeArgs(q="hello"))
    assert result.n == 5
    assert [p.type for p in emitter.packets] == ["fake_call", "fake_end"]
    assert emitter.packets[-1].status == "ok"
    assert emitter.packets[-1].result.n == 5


def test_emit_end_error_carries_message():
    emitter = _ListEmitter()
    tool = _FakeTool(emitter=emitter)
    tool.emit_end_error("tc_3", "Boom")
    assert emitter.packets[-1].status == "error"
    assert emitter.packets[-1].error == "Boom"
