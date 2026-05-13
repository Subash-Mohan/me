"""Sessions service layer.

Pure-Python service surface the API and the chat endpoint talk to. Single
durable Postgres row per session and per message-half. Cross-session state
is intentionally absent — `search_memories` is the only path to long-term
recall.
"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from typing import Any, Final, Literal, TypedDict
from uuid import UUID

import structlog
from sqlalchemy import and_, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session as DbSession

from app.models.message import Message
from app.models.session import Session

log = structlog.get_logger(__name__)

__all__ = [
    "MAX_PAGE_LIMIT",
    "TITLE_AUTOFILL_CHARS",
    "HistoryTurn",
    "SessionNotFound",
    "create_session",
    "delete_session",
    "find_assistant_for_user_message",
    "get_session",
    "list_session_messages",
    "list_sessions",
    "load_recent_history",
    "record_assistant_message",
    "record_user_message",
]

MAX_PAGE_LIMIT: Final[int] = 200
TITLE_AUTOFILL_CHARS: Final[int] = 60

_CURSOR_VERSION = 1


class SessionNotFound(Exception):
    """The session does not exist, is soft-deleted, or belongs to another user."""


class HistoryTurn(TypedDict):
    role: Literal["user", "assistant"]
    content: str


# ─── cursor helpers ────────────────────────────────────────────────────────


def _encode_cursor(ts: datetime, row_id: UUID) -> str:
    payload = json.dumps(
        {"v": _CURSOR_VERSION, "ts": ts.isoformat(), "id": str(row_id)},
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        padding = "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(cursor + padding)
        payload = json.loads(raw)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("malformed cursor") from exc

    if not isinstance(payload, dict) or payload.get("v") != _CURSOR_VERSION:
        raise ValueError("malformed cursor")

    ts = payload.get("ts")
    rid = payload.get("id")
    if not isinstance(ts, str) or not isinstance(rid, str):
        raise ValueError("malformed cursor")

    try:
        return datetime.fromisoformat(ts), UUID(rid)
    except ValueError as exc:
        raise ValueError("malformed cursor") from exc


def _clamp_limit(limit: int) -> int:
    return max(1, min(limit, MAX_PAGE_LIMIT))


# ─── sessions CRUD ─────────────────────────────────────────────────────────


def create_session(db: DbSession, *, user_id: UUID, title: str | None = None) -> Session:
    """Create a new chat session.

    `last_message_at` is stamped to `now()` on creation so list ordering by
    `last_message_at DESC` never has to deal with NULL.
    """
    session = Session(
        user_id=user_id,
        title=title,
        last_message_at=datetime.now(UTC),
    )
    db.add(session)
    db.flush()
    db.commit()
    db.refresh(session)
    return session


def get_session(db: DbSession, *, user_id: UUID, session_id: UUID) -> Session:
    row = db.execute(
        select(Session).where(
            Session.id == session_id,
            Session.user_id == user_id,
            Session.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if row is None:
        raise SessionNotFound(str(session_id))
    return row


def list_sessions(
    db: DbSession,
    *,
    user_id: UUID,
    cursor: str | None = None,
    limit: int = 50,
) -> tuple[list[Session], str | None]:
    """Cursor-paginated list of the user's sessions, newest-active first.

    Ordering is `(last_message_at DESC, id DESC)`; the cursor encodes that
    tuple so callers can resume mid-page deterministically.
    """
    limit = _clamp_limit(limit)

    stmt = (
        select(Session)
        .where(Session.user_id == user_id, Session.deleted_at.is_(None))
        .order_by(Session.last_message_at.desc(), Session.id.desc())
        .limit(limit + 1)
    )

    if cursor is not None:
        cur_ts, cur_id = _decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                Session.last_message_at < cur_ts,
                and_(Session.last_message_at == cur_ts, Session.id < cur_id),
            )
        )

    rows = list(db.execute(stmt).scalars().all())

    if len(rows) > limit:
        last_session = rows[limit - 1]
        # `last_message_at` is never NULL after create_session — narrow for ty.
        assert last_session.last_message_at is not None
        next_cursor: str | None = _encode_cursor(last_session.last_message_at, last_session.id)
        rows = rows[:limit]
    else:
        next_cursor = None

    return rows, next_cursor


def list_session_messages(
    db: DbSession,
    *,
    session: Session,
    cursor: str | None = None,
    limit: int = 50,
) -> tuple[list[Message], str | None]:
    """Cursor-paginated messages within one session, oldest-first.

    Caller is expected to have already proven ownership via `get_session`.
    """
    limit = _clamp_limit(limit)

    stmt = (
        select(Message)
        .where(Message.session_id == session.id, Message.deleted_at.is_(None))
        .order_by(Message.created_at.asc(), Message.id.asc())
        .limit(limit + 1)
    )
    if cursor is not None:
        cur_ts, cur_id = _decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                Message.created_at > cur_ts,
                and_(Message.created_at == cur_ts, Message.id > cur_id),
            )
        )

    rows = list(db.execute(stmt).scalars().all())
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor: str | None = _encode_cursor(last.created_at, last.id)
        rows = rows[:limit]
    else:
        next_cursor = None

    return rows, next_cursor


def delete_session(db: DbSession, *, user_id: UUID, session_id: UUID) -> None:
    """Soft-delete a session and all its messages in one transaction.

    Idempotent: already-deleted sessions are a no-op (not an error)."""
    row = db.execute(
        select(Session).where(Session.id == session_id, Session.user_id == user_id)
    ).scalar_one_or_none()
    if row is None:
        raise SessionNotFound(str(session_id))
    if row.deleted_at is not None:
        return None

    now = datetime.now(UTC)
    row.deleted_at = now
    db.execute(
        update(Message)
        .where(Message.session_id == session_id, Message.deleted_at.is_(None))
        .values(deleted_at=now)
    )
    db.commit()
    return None


# ─── per-turn writes ───────────────────────────────────────────────────────


def record_user_message(
    db: DbSession,
    *,
    user_id: UUID,
    session: Session,
    client_message_id: UUID,
    content: str,
    client_tz: str,
) -> Message:
    """Insert the user-message row keyed by `client_message_id`.

    PK conflict on `client_message_id` is treated as a successful retry — we
    return the existing row unchanged. The session's `last_message_at` is
    bumped only on a fresh insert (re-stamping on every retry would skew
    sidebar ordering). Title is auto-filled from the first ~60 chars when
    `session.title` is null.
    """
    stmt = (
        pg_insert(Message)
        .values(
            id=client_message_id,
            session_id=session.id,
            user_id=user_id,
            role="user",
            content=content,
            client_tz=client_tz,
        )
        .on_conflict_do_nothing(index_elements=["id"])
        .returning(Message.id)
    )
    new_id = db.execute(stmt).scalar_one_or_none()

    if new_id is None:
        # Same UUID came back — return the row that's already there.
        existing = db.execute(select(Message).where(Message.id == client_message_id)).scalar_one()
        return existing

    session.last_message_at = datetime.now(UTC)
    if session.title is None:
        session.title = content[:TITLE_AUTOFILL_CHARS]
    db.flush()
    db.commit()
    db.refresh(session)
    return db.execute(select(Message).where(Message.id == new_id)).scalar_one()


def record_assistant_message(
    db: DbSession,
    *,
    user_id: UUID,
    session: Session,
    parent_message_id: UUID,
    content: str,
    tool_activity: dict[str, Any] | None,
) -> Message:
    """Insert the assistant-message row.

    The partial UNIQUE on `parent_message_id` guards against double-write if
    the endpoint somehow flushes twice for the same turn. Caller is expected
    to have already streamed the deltas.
    """
    message = Message(
        session_id=session.id,
        user_id=user_id,
        role="assistant",
        content=content,
        tool_activity=tool_activity,
        parent_message_id=parent_message_id,
    )
    db.add(message)
    session.last_message_at = datetime.now(UTC)
    db.flush()
    db.commit()
    db.refresh(message)
    return message


def find_assistant_for_user_message(
    db: DbSession,
    *,
    user_message_id: UUID,
) -> Message | None:
    """Return the cached assistant reply for a user turn, or None if no run
    has completed yet (or the assistant row was soft-deleted)."""
    return db.execute(
        select(Message).where(
            Message.parent_message_id == user_message_id,
            Message.deleted_at.is_(None),
        )
    ).scalar_one_or_none()


def load_recent_history(
    db: DbSession,
    *,
    session_id: UUID,
    exclude_message_id: UUID,
    limit_pairs: int,
) -> list[HistoryTurn]:
    """Last `limit_pairs` user+assistant pairs in chronological order.

    `exclude_message_id` keeps the just-saved user message out of the
    history (the runtime passes it separately as `user_input`). The query
    fetches up to `2 * limit_pairs` rows ordered newest-first then reverses,
    so callers always see chronological turns.
    """
    rows = (
        db.execute(
            select(Message)
            .where(
                Message.session_id == session_id,
                Message.deleted_at.is_(None),
                Message.id != exclude_message_id,
            )
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(2 * limit_pairs)
        )
        .scalars()
        .all()
    )
    chrono = list(reversed(rows))
    return [{"role": r.role, "content": r.content} for r in chrono]
