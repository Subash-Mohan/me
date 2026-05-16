"""HTTP surface for chat sessions and their messages.

Thin shims over `app.services.sessions`. Every route is sync, parses input
via Pydantic, calls one service function, translates the typed domain
errors, and returns a Pydantic response.

`GET /sessions/{id}` returns metadata only; messages live on the dedicated
`GET /sessions/{id}/messages` route with reverse-chronological cursor
pagination — the shape a chat UI needs for "initial render + scroll up".
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session as DbSession

from app.core.security import current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.sessions import (
    MessageRead,
    MessagesPageResponse,
    SessionCreate,
    SessionListItem,
    SessionListResponse,
    SessionRead,
)
from app.services.sessions import (
    SessionNotFound,
    create_session,
    delete_session,
    get_session,
    list_session_messages,
    list_sessions,
)

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionRead, status_code=status.HTTP_201_CREATED)
def create(
    body: SessionCreate,
    user: Annotated[User, Depends(current_user)],
    db: Annotated[DbSession, Depends(get_db)],
) -> SessionRead:
    row = create_session(db, user_id=user.id, title=body.title)
    return SessionRead.model_validate(row)


@router.get("", response_model=SessionListResponse)
def list_items(
    user: Annotated[User, Depends(current_user)],
    db: Annotated[DbSession, Depends(get_db)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> SessionListResponse:
    try:
        sessions, next_cursor = list_sessions(db, user_id=user.id, cursor=cursor, limit=limit)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    items = [SessionListItem.model_validate(s) for s in sessions]
    return SessionListResponse(items=items, next_cursor=next_cursor)


@router.get("/{session_id}", response_model=SessionRead)
def detail(
    session_id: UUID,
    user: Annotated[User, Depends(current_user)],
    db: Annotated[DbSession, Depends(get_db)],
) -> SessionRead:
    try:
        session = get_session(db, user_id=user.id, session_id=session_id)
    except SessionNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found") from exc
    return SessionRead.model_validate(session)


@router.get("/{session_id}/messages", response_model=MessagesPageResponse)
def messages(
    session_id: UUID,
    user: Annotated[User, Depends(current_user)],
    db: Annotated[DbSession, Depends(get_db)],
    before: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> MessagesPageResponse:
    try:
        session = get_session(db, user_id=user.id, session_id=session_id)
    except SessionNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found") from exc

    try:
        rows, next_cursor = list_session_messages(
            db, session=session, cursor=before, limit=limit, direction="desc"
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    return MessagesPageResponse(
        items=[MessageRead.model_validate(m) for m in rows],
        next_cursor=next_cursor,
    )


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(
    session_id: UUID,
    user: Annotated[User, Depends(current_user)],
    db: Annotated[DbSession, Depends(get_db)],
) -> Response:
    try:
        delete_session(db, user_id=user.id, session_id=session_id)
    except SessionNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
