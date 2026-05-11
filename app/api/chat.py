"""Chat endpoint — async-streaming SSE wrapping `run_agent_stream`.

This is the project's only async route. CLAUDE.md cross-cutting rule 1 makes
HTTP and services sync; the carve-out exists because the OpenAI Agents SDK
streams from an async iterator. Sync alternatives (threads + queues) trade
readability for no benefit. See DECISIONS.md "chat agent runtime async carve-out".
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.agents import run_agent_stream
from app.core.deps import get_memory_client
from app.core.security import current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.chat import ChatRequest
from app.services.memory_client import MemoryClient

router = APIRouter(prefix="/chat", tags=["chat"])

log = structlog.get_logger(__name__)


@router.post("")
async def chat(
    body: ChatRequest,
    user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
    memory_client: Annotated[MemoryClient, Depends(get_memory_client)],
) -> StreamingResponse:
    now_utc = datetime.now(UTC).isoformat(timespec="seconds")
    log.info(
        "chat.start",
        user_id=str(user.id),
        message_len=len(body.message),
        client_tz=body.client_tz,
    )

    async def sse() -> AsyncIterator[str]:
        async for packet in run_agent_stream(
            body.message,
            db=db,
            memory_client=memory_client,
            user=user,
            now_utc=now_utc,
            client_tz=body.client_tz,
        ):
            yield f"data: {packet.model_dump_json()}\n\n"

    return StreamingResponse(sse(), media_type="text/event-stream")
