"""HTTP surface for the memory layer.

Thin shims over `app.services.memory`. Every route is sync, parses input via
Pydantic, calls one service method, translates the typed domain errors, and
returns a Pydantic response.

`MemoryClient*` errors never reach this layer — the service swallows them and
records `external_status='unsynced'` (or `'pending_delete'` on DELETE).
Local writes always succeed at the HTTP boundary; callers retry the remote
side via `POST /memories/{id}/sync`.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.deps import get_memory_client
from app.core.security import confirm_passphrase, current_user
from app.db.session import get_db
from app.models.memory import Memory
from app.models.user import User
from app.schemas.memory import (
    MemoryCard,
    MemoryCreate,
    MemoryDetail,
    MemoryListResponse,
    MemoryPatch,
    MemorySearchResponse,
    SearchHit,
)
from app.services._memory_helpers import text_preview
from app.services.memory import (
    MemoryDuplicate,
    MemoryIdempotencyReused,
    MemoryNotFound,
    MemoryValidationError,
    create_memory,
    delete_memory,
    get_memory,
    list_memories,
    search_memories,
    sync_memory,
    update_memory,
)
from app.services.memory_client import MemoryClient

router = APIRouter(prefix="/memories", tags=["memories"])


def _to_card(row: Memory) -> MemoryCard:
    return MemoryCard(
        id=row.id,
        event_date=row.event_date,
        location_label=row.location_label,
        text_preview=text_preview(row.text),
        external_status=row.external_status,
    )


# ─── create ────────────────────────────────────────────────────────────────


@router.post("", response_model=MemoryDetail, status_code=status.HTTP_201_CREATED)
def create(
    body: MemoryCreate,
    user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
    client: Annotated[MemoryClient, Depends(get_memory_client)],
) -> MemoryDetail:
    try:
        row = create_memory(
            db,
            client,
            user_id=user.id,
            text=body.text,
            event_date=body.event_date,
            event_tz=body.event_tz,
            event_time=body.event_time,
            location_lat=body.location_lat,
            location_lng=body.location_lng,
            location_label=body.location_label,
            idempotency_id=body.idempotency_id,
        )
    except MemoryValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except MemoryIdempotencyReused as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "idempotency_id reused") from exc

    return MemoryDetail.model_validate(row)


# ─── list ──────────────────────────────────────────────────────────────────


@router.get("", response_model=MemoryListResponse)
def list_(
    user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
    from_date: Annotated[str | None, Query()] = None,
    to_date: Annotated[str | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> MemoryListResponse:
    parsed_from: date | None = None
    parsed_to: date | None = None
    if from_date is not None:
        try:
            parsed_from = date.fromisoformat(from_date)
        except ValueError as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, f"invalid from_date: {from_date!r}"
            ) from exc
    if to_date is not None:
        try:
            parsed_to = date.fromisoformat(to_date)
        except ValueError as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, f"invalid to_date: {to_date!r}"
            ) from exc

    try:
        rows, next_cursor = list_memories(
            db,
            user_id=user.id,
            from_date=parsed_from,
            to_date=parsed_to,
            cursor=cursor,
            limit=limit,
        )
    except MemoryValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    return MemoryListResponse(
        items=[_to_card(r) for r in rows],
        next_cursor=next_cursor,
    )


# ─── search (declared before /{memory_id} so "search" doesn't 422 as a UUID) ──


@router.get("/search", response_model=MemorySearchResponse)
def search(
    user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
    client: Annotated[MemoryClient, Depends(get_memory_client)],
    q: Annotated[str, Query(min_length=1)],
    limit: Annotated[int, Query(ge=1, le=200)] = 10,
) -> MemorySearchResponse:
    result = search_memories(db, client, user_id=user.id, q=q, limit=limit)
    return MemorySearchResponse(
        items=[SearchHit(memory=_to_card(row), similarity=score) for row, score in result.hits],
        source=result.source,
    )


# ─── detail ────────────────────────────────────────────────────────────────


@router.get("/{memory_id}", response_model=MemoryDetail)
def detail(
    memory_id: UUID,
    user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> MemoryDetail:
    try:
        row = get_memory(db, user_id=user.id, memory_id=memory_id)
    except MemoryNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "memory not found") from exc
    return MemoryDetail.model_validate(row)


# ─── patch ─────────────────────────────────────────────────────────────────


@router.patch("/{memory_id}", response_model=MemoryDetail)
def patch(
    memory_id: UUID,
    body: MemoryPatch,
    user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
    client: Annotated[MemoryClient, Depends(get_memory_client)],
) -> MemoryDetail:
    # Only forward fields the caller actually supplied — otherwise the service
    # sees `None` for omitted fields and clobbers existing values.
    kwargs: dict[str, Any] = {field: getattr(body, field) for field in body.model_fields_set}
    try:
        row = update_memory(db, client, user_id=user.id, memory_id=memory_id, **kwargs)
    except MemoryNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "memory not found") from exc
    except MemoryDuplicate as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except MemoryValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    return MemoryDetail.model_validate(row)


# ─── delete (step-up via X-Confirm-Passphrase) ─────────────────────────────


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(
    memory_id: UUID,
    user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
    client: Annotated[MemoryClient, Depends(get_memory_client)],
    _: Annotated[None, Depends(confirm_passphrase)],
) -> Response:
    try:
        delete_memory(db, client, user_id=user.id, memory_id=memory_id)
    except MemoryNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "memory not found") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ─── sync ──────────────────────────────────────────────────────────────────


@router.post("/{memory_id}/sync", response_model=MemoryDetail)
def sync(
    memory_id: UUID,
    user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
    client: Annotated[MemoryClient, Depends(get_memory_client)],
) -> MemoryDetail:
    try:
        row = sync_memory(db, client, user_id=user.id, memory_id=memory_id)
    except MemoryNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "memory not found") from exc
    return MemoryDetail.model_validate(row)
