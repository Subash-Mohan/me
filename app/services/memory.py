"""Memory service layer.

Pure-Python service surface the API and the chat agent talk to. Local Postgres
is the source of truth; Supermemory is a derived index reached via the
`MemoryClient` Protocol. External-API failures never block local writes — the
row is persisted with `external_status='unsynced'` and surfaced for retry.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Any, Final, Literal, NamedTuple
from uuid import UUID

import structlog
from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.memory import Memory
from app.services.memory_client import (
    MemoryClient,
    MemoryClientError,
    MemoryClientPermanentError,
)

log = structlog.get_logger(__name__)

# Service-level cap on `limit` for `list_memories` / `search_memories`.
# Defense in depth for non-HTTP callers (CLI, tests, future agent code) since
# Pydantic validation only guards the route layer.
MAX_PAGE_LIMIT: Final[int] = 200


# Sentinel for `update_memory` patch semantics: distinguishes
# "field cleared to None" from "field not provided at all".
_UNSET: Final = object()


# ─── typed errors ──────────────────────────────────────────────────────────


class MemoryNotFound(KeyError):
    """The memory does not exist for this user, or has been soft-deleted."""


class MemoryDuplicate(ValueError):
    """Another non-deleted row already has the same (user_id, content_hash)."""


class MemoryValidationError(ValueError):
    """Caller-side validation failure (bad TZ, lat/lng pairing, etc.)."""


# Helper imports live below the error classes so the helpers (which import
# `MemoryValidationError` to raise it) can complete loading without a cycle.
from app.services._memory_helpers import (  # noqa: E402
    canonical_hash,
    decode_cursor,
    encode_cursor,
    validate_tz,
)

# ─── read-only methods ─────────────────────────────────────────────────────


def _clamp_limit(limit: int) -> int:
    return max(1, min(limit, MAX_PAGE_LIMIT))


def get_memory(db: Session, *, user_id: UUID, memory_id: UUID) -> Memory:
    row = db.execute(
        select(Memory).where(
            Memory.id == memory_id,
            Memory.user_id == user_id,
            Memory.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if row is None:
        raise MemoryNotFound(str(memory_id))
    return row


def list_memories(
    db: Session,
    *,
    user_id: UUID,
    from_date: date | None = None,
    to_date: date | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> tuple[list[Memory], str | None]:
    """Cursor-paginated, descending by `(event_date, id)`.

    `next_cursor` is `None` when the page is final. The returned list always
    has at most `limit` rows (post-clamp); the partial-index `(user_id,
    event_date DESC, id DESC) WHERE deleted_at IS NULL` from 05a backs the
    keyset comparison.
    """
    limit = _clamp_limit(limit)

    where = [Memory.user_id == user_id, Memory.deleted_at.is_(None)]
    if from_date is not None:
        where.append(Memory.event_date >= from_date)
    if to_date is not None:
        where.append(Memory.event_date <= to_date)
    if cursor is not None:
        cur_date, cur_id = decode_cursor(cursor)
        # Composite keyset: (event_date, id) lexicographically less than the cursor.
        where.append(
            or_(
                Memory.event_date < cur_date,
                and_(Memory.event_date == cur_date, Memory.id < cur_id),
            )
        )

    rows = list(
        db.execute(
            select(Memory)
            .where(*where)
            .order_by(Memory.event_date.desc(), Memory.id.desc())
            .limit(limit + 1)
        )
        .scalars()
        .all()
    )

    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor: str | None = encode_cursor(last.event_date, last.id)
        rows = rows[:limit]
    else:
        next_cursor = None

    return rows, next_cursor


# ─── write methods ─────────────────────────────────────────────────────────


def _validate_location_pair(lat: float | None, lng: float | None) -> None:
    if (lat is None) != (lng is None):
        raise MemoryValidationError("location_lat and location_lng must be set together")
    if lat is not None and not -90 <= lat <= 90:
        raise MemoryValidationError("location_lat out of range")
    if lng is not None and not -180 <= lng <= 180:
        raise MemoryValidationError("location_lng out of range")


def _build_metadata(row: Memory) -> dict[str, str | float | bool | list[str]]:
    """Supermemory metadata envelope. Kept narrow — no nested dicts.

    Includes the event date (queryable), the timezone, the local creation
    timestamp as unix seconds, and the human-readable location label when
    present. Numeric coordinates are deliberately omitted from metadata; they
    live only in the local row.
    """
    metadata: dict[str, str | float | bool | list[str]] = {
        "event_date": row.event_date.isoformat(),
        "event_tz": row.event_tz,
        "created_at_unix": int(row.created_at.timestamp()),
    }
    if row.location_label:
        metadata["location_label"] = row.location_label
    return metadata


def _container_tag(user_id: UUID) -> str:
    return f"user_{user_id.hex}"


def _send_to_supermemory_add(
    client: MemoryClient,
    row: Memory,
    *,
    op_label: str = "add",
) -> None:
    """Issue `client.add(...)` for `row`, mutating `row.external_*` based on outcome.

    Never re-raises — the row stays durable locally regardless. Permanent
    errors (4xx caller-bug class) emit a separate WARNING so ops can
    distinguish caller-bugs from transient blips.
    """
    try:
        result = client.add(
            custom_id=row.id,
            content=row.text,
            container_tags=[_container_tag(row.user_id)],
            metadata=_build_metadata(row),
        )
    except MemoryClientError as err:
        if isinstance(err, MemoryClientPermanentError):
            log.warning(
                "memory.external_permanent_err",
                op=op_label,
                memory_id=str(row.id),
                error_class=type(err).__name__,
            )
        row.external_status = "unsynced"
        row.external_error = type(err).__name__
        return

    row.external_id = result.doc_id
    row.external_status = "synced"
    row.external_synced_at = datetime.now(UTC)
    row.external_error = None


def create_memory(
    db: Session,
    client: MemoryClient,
    *,
    user_id: UUID,
    text: str,
    event_date: date,
    event_tz: str,
    event_time: time | None = None,
    location_lat: float | None = None,
    location_lng: float | None = None,
    location_label: str | None = None,
    idempotency_id: UUID | None = None,
) -> Memory:
    text = text.strip()
    if not text:
        raise MemoryValidationError("text cannot be empty")
    validate_tz(event_tz)
    _validate_location_pair(location_lat, location_lng)

    # Layer-1 dedupe: same idempotency_id from this user → return existing row.
    if idempotency_id is not None:
        existing = db.execute(
            select(Memory).where(
                Memory.id == idempotency_id,
                Memory.user_id == user_id,
                Memory.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing

    digest = canonical_hash(text)
    values: dict[str, Any] = {
        "user_id": user_id,
        "text": text,
        "event_date": event_date,
        "event_tz": event_tz,
        "event_time": event_time,
        "location_lat": location_lat,
        "location_lng": location_lng,
        "location_label": location_label,
        "content_hash": digest,
    }
    if idempotency_id is not None:
        values["id"] = idempotency_id

    stmt = (
        pg_insert(Memory)
        .values(**values)
        .on_conflict_do_nothing(
            index_elements=["user_id", "content_hash"],
            index_where=Memory.deleted_at.is_(None),
        )
        .returning(Memory.id)
    )
    new_id = db.execute(stmt).scalar_one_or_none()

    if new_id is None:
        # Layer-2 dedupe: a non-deleted row with the same canonical hash
        # already exists for this user. Return it; do not re-call the client.
        return db.execute(
            select(Memory).where(
                Memory.user_id == user_id,
                Memory.content_hash == digest,
                Memory.deleted_at.is_(None),
            )
        ).scalar_one()

    db.flush()
    row = db.execute(select(Memory).where(Memory.id == new_id)).scalar_one()

    _send_to_supermemory_add(client, row)

    db.commit()
    db.refresh(row)
    return row


def update_memory(
    db: Session,
    client: MemoryClient,
    *,
    user_id: UUID,
    memory_id: UUID,
    text: Any = _UNSET,
    event_date: Any = _UNSET,
    event_time: Any = _UNSET,
    event_tz: Any = _UNSET,
    location_lat: Any = _UNSET,
    location_lng: Any = _UNSET,
    location_label: Any = _UNSET,
) -> Memory:
    row = db.execute(
        select(Memory).where(
            Memory.id == memory_id,
            Memory.user_id == user_id,
            Memory.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if row is None:
        raise MemoryNotFound(str(memory_id))

    if event_tz is not _UNSET:
        validate_tz(event_tz)

    # Validate the *resulting* lat/lng pair after merging the patch over the
    # existing row, so the DB CHECKs stay defense-in-depth.
    if location_lat is not _UNSET or location_lng is not _UNSET:
        new_lat = location_lat if location_lat is not _UNSET else row.location_lat
        new_lng = location_lng if location_lng is not _UNSET else row.location_lng
        _validate_location_pair(new_lat, new_lng)

    text_changed = False
    if text is not _UNSET:
        stripped = text.strip()
        if not stripped:
            raise MemoryValidationError("text cannot be empty")
        if stripped != row.text:
            row.text = stripped
            row.content_hash = canonical_hash(stripped)
            text_changed = True

    if event_date is not _UNSET:
        row.event_date = event_date
    if event_time is not _UNSET:
        row.event_time = event_time
    if event_tz is not _UNSET:
        row.event_tz = event_tz
    if location_lat is not _UNSET:
        row.location_lat = location_lat
    if location_lng is not _UNSET:
        row.location_lng = location_lng
    if location_label is not _UNSET:
        row.location_label = location_label

    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        if text_changed:
            raise MemoryDuplicate("another memory already has the same text") from exc
        raise

    if row.external_id is None:
        _send_to_supermemory_add(client, row, op_label="add")
    else:
        _send_to_supermemory_patch(client, row, content_changed=text_changed)

    db.commit()
    db.refresh(row)
    return row


def _send_to_supermemory_patch(client: MemoryClient, row: Memory, *, content_changed: bool) -> None:
    """Issue `client.patch(...)` for `row`. Mirrors `_send_to_supermemory_add`'s
    failure handling — never re-raises, marks `unsynced` on error, ops-logs on
    permanent errors."""
    assert row.external_id is not None  # caller checked
    try:
        client.patch(
            doc_id=row.external_id,
            content=row.text if content_changed else None,
            metadata=_build_metadata(row),
        )
    except MemoryClientError as err:
        if isinstance(err, MemoryClientPermanentError):
            log.warning(
                "memory.external_permanent_err",
                op="patch",
                memory_id=str(row.id),
                error_class=type(err).__name__,
            )
        row.external_status = "unsynced"
        row.external_error = type(err).__name__
        return

    row.external_status = "synced"
    row.external_synced_at = datetime.now(UTC)
    row.external_error = None


def delete_memory(
    db: Session,
    client: MemoryClient,
    *,
    user_id: UUID,
    memory_id: UUID,
) -> None:
    row = db.execute(
        select(Memory).where(Memory.id == memory_id, Memory.user_id == user_id)
    ).scalar_one_or_none()

    if row is None:
        raise MemoryNotFound(str(memory_id))

    if row.deleted_at is not None:
        # Idempotent: already soft-deleted, no-op.
        return None

    row.deleted_at = datetime.now(UTC)
    external_id = row.external_id

    if external_id is not None:
        try:
            client.delete(doc_id=external_id)
        except MemoryClientError as err:
            if isinstance(err, MemoryClientPermanentError):
                log.warning(
                    "memory.external_permanent_err",
                    op="delete",
                    memory_id=str(row.id),
                    error_class=type(err).__name__,
                )
            row.external_status = "pending_delete"
            row.external_error = type(err).__name__

    db.commit()
    return None


# ─── search ────────────────────────────────────────────────────────────────


class SearchResult(NamedTuple):
    hits: list[tuple[Memory, float | None]]
    source: Literal["supermemory", "local"]


def search_memories(
    db: Session,
    client: MemoryClient,
    *,
    user_id: UUID,
    q: str,
    limit: int = 10,
) -> SearchResult:
    """Vector search via Supermemory; local FTS fallback on any client error.

    The returned hits are ORM rows paired with similarity scores. Local-fallback
    hits set `similarity=None` — `ts_rank_cd` ranks aren't comparable to vector
    similarities, so they are not exposed.
    """
    limit = _clamp_limit(limit)

    try:
        sm_hits = client.search(
            q=q,
            container_tag=_container_tag(user_id),
            limit=limit,
        )
    except MemoryClientError as err:
        log.warning(
            "memory.search_fallback",
            user_id=str(user_id),
            error_class=type(err).__name__,
        )
        return _search_local_fallback(db, user_id=user_id, q=q, limit=limit)

    if not sm_hits:
        log.info("memory.search_ok", user_id=str(user_id), count=0, source="supermemory")
        return SearchResult(hits=[], source="supermemory")

    doc_ids = [h.doc_id for h in sm_hits]
    rows = (
        db.execute(
            select(Memory).where(
                Memory.external_id.in_(doc_ids),
                Memory.user_id == user_id,
                Memory.deleted_at.is_(None),
            )
        )
        .scalars()
        .all()
    )
    by_doc_id = {r.external_id: r for r in rows}

    hits: list[tuple[Memory, float | None]] = []
    for h in sm_hits:
        row = by_doc_id.get(h.doc_id)
        if row is not None:
            hits.append((row, h.similarity))

    log.info(
        "memory.search_ok",
        user_id=str(user_id),
        count=len(hits),
        source="supermemory",
    )
    return SearchResult(hits=hits, source="supermemory")


def _search_local_fallback(db: Session, *, user_id: UUID, q: str, limit: int) -> SearchResult:
    tsquery = func.plainto_tsquery("simple", q)
    rows = (
        db.execute(
            select(Memory)
            .where(
                Memory.user_id == user_id,
                Memory.deleted_at.is_(None),
                Memory.search_tsv.op("@@")(tsquery),
            )
            .order_by(func.ts_rank_cd(Memory.search_tsv, tsquery).desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    hits: list[tuple[Memory, float | None]] = [(r, None) for r in rows]
    log.info("memory.search_ok", user_id=str(user_id), count=len(hits), source="local")
    return SearchResult(hits=hits, source="local")


# ─── sync ──────────────────────────────────────────────────────────────────


def sync_memory(
    db: Session,
    client: MemoryClient,
    *,
    user_id: UUID,
    memory_id: UUID,
) -> Memory:
    """Drive one row toward `external_status='synced'` based on its current state.

    `pending_delete` rows are reachable here even though they are locally
    soft-deleted — the retry exists precisely to push the remote-side delete
    through. Other states behave the way the inline create/update path would.
    """
    row = db.execute(
        select(Memory).where(Memory.id == memory_id, Memory.user_id == user_id)
    ).scalar_one_or_none()
    if row is None:
        raise MemoryNotFound(str(memory_id))

    status = row.external_status

    if status == "synced":
        return row

    if status == "unsynced":
        if row.external_id is None:
            _send_to_supermemory_add(client, row)
        else:
            _send_to_supermemory_patch(client, row, content_changed=True)
    elif status == "pending_delete":
        if row.external_id is None:
            # Inconsistent state — nothing to delete remotely. Settle locally.
            row.external_status = "synced"
            row.external_error = None
        else:
            try:
                client.delete(doc_id=row.external_id)
            except MemoryClientError as err:
                if isinstance(err, MemoryClientPermanentError):
                    log.warning(
                        "memory.external_permanent_err",
                        op="delete",
                        memory_id=str(row.id),
                        error_class=type(err).__name__,
                    )
                row.external_error = type(err).__name__
                # Stay in pending_delete.
            else:
                row.external_status = "synced"
                row.external_error = None

    db.commit()
    db.refresh(row)
    return row
