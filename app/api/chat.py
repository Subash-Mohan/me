"""Chat endpoint — async-streaming SSE wrapping `run_agent_stream`.

This is the project's only async route. Sync-route discipline is suspended
here because the OpenAI Agents SDK streams from an async iterator; sync
alternatives (threads + queues) trade readability for no benefit.

Stream-folding state, SSE framing, and end-of-stream persistence live in
`app/api/_chat_stream.py`. This file is purely HTTP/DI orchestration:
resolve session, record the user turn, decide replay-vs-fresh, hand the
inputs to a streaming function.
"""

import asyncio
from datetime import UTC, datetime
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session as DbSession

from app.api._chat_stream import ChatTurn, replay_stream, stream_turn
from app.core.config import get_settings
from app.core.deps import get_memory_client
from app.core.security import current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.chat import ChatRequest
from app.services.memory_client import MemoryClient
from app.services.sessions import (
    SessionNotFound,
    find_assistant_for_user_message,
    get_session,
    load_recent_history,
    record_user_message,
)

router = APIRouter(prefix="/chat", tags=["chat"])

log = structlog.get_logger(__name__)


@router.post("")
async def chat(
    body: ChatRequest,
    user: Annotated[User, Depends(current_user)],
    db: Annotated[DbSession, Depends(get_db)],
    memory_client: Annotated[MemoryClient, Depends(get_memory_client)],
) -> StreamingResponse:
    now_utc = datetime.now(UTC).isoformat(timespec="seconds")
    log.info(
        "chat.start",
        user_id=str(user.id),
        session_id=str(body.session_id),
        client_message_id=str(body.client_message_id),
        message_len=len(body.message),
        client_tz=body.client_tz,
    )

    try:
        session = await asyncio.to_thread(
            get_session, db, user_id=user.id, session_id=body.session_id
        )
    except SessionNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found") from exc

    await asyncio.to_thread(
        record_user_message,
        db,
        user_id=user.id,
        session=session,
        client_message_id=body.client_message_id,
        content=body.message,
        client_tz=body.client_tz,
    )

    cached = await asyncio.to_thread(
        find_assistant_for_user_message,
        db,
        user_message_id=body.client_message_id,
    )

    if cached is not None:
        log.info(
            "chat.replay",
            user_id=str(user.id),
            client_message_id=str(body.client_message_id),
        )
        return StreamingResponse(replay_stream(cached.content), media_type="text/event-stream")

    history = await asyncio.to_thread(
        load_recent_history,
        db,
        session_id=body.session_id,
        exclude_message_id=body.client_message_id,
        limit_pairs=get_settings().chat_history_turns,
    )

    turn = ChatTurn(
        db=db,
        user=user,
        session=session,
        body=body,
        memory_client=memory_client,
        history=history,
        now_utc=now_utc,
    )
    return StreamingResponse(stream_turn(turn), media_type="text/event-stream")
