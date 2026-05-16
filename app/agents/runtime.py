import asyncio
import logging
from collections.abc import AsyncIterator, Sequence
from typing import Any

from agents import Agent, FunctionTool, Runner
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from agents.tool_context import ToolContext
from openai import AsyncOpenAI
from sqlalchemy.orm import Session

from app.agents.context import AgentContext
from app.agents.emitter import Emitter
from app.agents.instructions import render_system_prompt
from app.agents.packets import ErrorPacket
from app.agents.sse import translate_framework
from app.agents.tools import ALL_TOOL_CLASSES, Packet
from app.agents.tools._base import Tool
from app.core.config import get_settings
from app.models.user import User
from app.services.memory_client import MemoryClient
from app.services.sessions import HistoryTurn

log = logging.getLogger(__name__)
_SENTINEL: Any = object()


def _adapt(tool: Tool) -> FunctionTool:
    async def on_invoke_tool(
        ctx: ToolContext[AgentContext],
        args_json: str,
    ) -> str:
        args = tool.ARGS_MODEL.model_validate_json(args_json or "{}")
        # ToolContext.tool_call_id is typed `str | <sentinel>`; the SDK sets it
        # to a real str whenever this callback fires.
        tool_call_id = ctx.tool_call_id if isinstance(ctx.tool_call_id, str) else ""
        result = await tool.run(ctx.context, tool_call_id, args)
        return result.model_dump_json()

    return FunctionTool(
        name=tool.NAME,
        description=tool.DESCRIPTION,
        params_json_schema=tool.ARGS_MODEL.model_json_schema(),
        on_invoke_tool=on_invoke_tool,
    )


def build_agent(
    emitter: Emitter,
    *,
    now_utc: str,
    client_tz: str,
) -> Agent[AgentContext]:
    settings = get_settings()
    client = AsyncOpenAI(
        api_key=settings.openrouter_api_key.get_secret_value(),
        base_url="https://openrouter.ai/api/v1",
    )
    model = OpenAIChatCompletionsModel(
        model=settings.openrouter_default_model,
        openai_client=client,
    )
    tools = [cls(emitter=emitter) for cls in ALL_TOOL_CLASSES]
    return Agent(
        name="me-chat",
        instructions=render_system_prompt(now_utc=now_utc, client_tz=client_tz),
        model=model,
        tools=[_adapt(t) for t in tools],
    )


def _build_input(
    user_input: str,
    history: Sequence[HistoryTurn] | None,
) -> Any:
    """Either the bare user message (no history) or a chronological list of
    `{role, content}` items with the user message appended last.

    Return type is `Any` because the SDK's `Runner.run_streamed` accepts a
    union of TypedDict shapes that we can't construct precisely without
    coupling to internal SDK types.

    Returning the bare string in the no-history case keeps the runtime
    behaviour byte-identical to phase 12 for the smoke test, which passes
    no history."""
    if not history:
        return user_input
    items: list[dict[str, str]] = [
        {"role": turn["role"], "content": turn["content"]} for turn in history
    ]
    items.append({"role": "user", "content": user_input})
    return items


async def run_agent_stream(
    user_input: str,
    db: Session,
    memory_client: MemoryClient,
    user: User,
    *,
    now_utc: str,
    client_tz: str,
    history: Sequence[HistoryTurn] | None = None,
) -> AsyncIterator[Packet]:
    queue: asyncio.Queue = asyncio.Queue()
    emitter = Emitter(queue, asyncio.get_running_loop())
    agent = build_agent(emitter, now_utc=now_utc, client_tz=client_tz)
    ctx = AgentContext(db=db, memory_client=memory_client, user=user, emitter=emitter)
    agent_input = _build_input(user_input, history)

    async def drive() -> None:
        try:
            result = Runner.run_streamed(agent, input=agent_input, context=ctx)
            async for sdk_event in result.stream_events():
                for packet in translate_framework(sdk_event):
                    emitter.emit(packet)
        except Exception as exc:
            log.exception("agent_stream_failed: %s", type(exc).__name__)
            emitter.emit(ErrorPacket(code="agent_failed", message=type(exc).__name__))
        finally:
            emitter.emit(_SENTINEL)

    task = asyncio.create_task(drive())
    try:
        while True:
            packet = await queue.get()
            if packet is _SENTINEL:
                return
            yield packet
    finally:
        if not task.done():
            task.cancel()
