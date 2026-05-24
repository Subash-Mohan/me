from typing import Any, Literal

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

    def run(self, ctx: Any, tool_call_id: str, args: _FakeArgs) -> _FakeResult:
        return _FakeResult(n=len(args.q))


def test_run_returns_typed_result():
    tool = _FakeTool()
    result = tool.run(ctx=None, tool_call_id="tc_2", args=_FakeArgs(q="hello"))
    assert result.n == 5


def test_packet_classes_are_declared_on_subclass():
    """Concrete tools must declare the three packet classes. The runtime
    looks these up by attribute when emitting lifecycle packets."""
    tool = _FakeTool()
    assert tool.START_PACKET is _StartPkt
    assert tool.CALL_PACKET is _CallPkt
    assert tool.END_PACKET is _EndPkt
