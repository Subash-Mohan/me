"""Helpers for chat-agent evals.

Each eval drives `run_agent_stream` with a fixed `now_utc` (so date logic is
deterministic) and a `FakeMemoryClient` (so memory state is whatever the
test seeded). The model call goes to real OpenRouter.

`tool_call_names` / `tool_call_args` / `final_text` are the assertion
primitives — packets are heterogeneous, so picking out what you care about
beats trying to type-check the union at the eval site.
"""

from __future__ import annotations

from typing import Any

from app.agents import run_agent_stream

# Fixed clock so "yesterday"/"last night"/"today" resolve identically every run.
EVAL_NOW_UTC = "2026-05-09T16:00:00+00:00"
EVAL_NOW_DATE = "2026-05-09"
EVAL_YESTERDAY_DATE = "2026-05-08"
EVAL_TZ = "America/New_York"


def run_chat(
    *,
    message: str,
    db: Any,
    memory_client: Any,
    user: Any,
    now_utc: str = EVAL_NOW_UTC,
    client_tz: str = EVAL_TZ,
) -> list[Any]:
    """Drive the agent and return every packet it emits, in order."""
    return list(
        run_agent_stream(
            message,
            db=db,
            memory_client=memory_client,
            user=user,
            now_utc=now_utc,
            client_tz=client_tz,
        )
    )


def tool_call_names(packets: list[Any]) -> list[str]:
    """Tool name for each `<tool>_call` packet, in stream order."""
    out: list[str] = []
    for p in packets:
        t: str = p.type
        if t.endswith("_call") and hasattr(p, "arguments"):
            out.append(t.removesuffix("_call"))
    return out


def tool_call_args(packets: list[Any], tool_name: str) -> list[dict[str, Any]]:
    """All argument dicts for calls of `tool_name`, in stream order.

    Uses `mode="json"` so dates/times/UUIDs come out as strings — matches the
    wire format the frontend would see and keeps assertions readable.
    """
    return [
        p.arguments.model_dump(mode="json")
        for p in packets
        if p.type == f"{tool_name}_call" and hasattr(p, "arguments")
    ]


def final_text(packets: list[Any]) -> str:
    """Concatenated text the user would see (all `text_delta` packets)."""
    return "".join(p.delta for p in packets if p.type == "text_delta")
