"""Memory backend client.

`MemoryClient` is the vendor-agnostic Protocol the rest of the app talks to.
`SupermemoryClient` is the production implementation, delegating to the official
`supermemory` SDK and translating its exception taxonomy to `MemoryClientError`s.
A second backend would be a new class implementing `MemoryClient`; nothing else
in the app would change.

Privacy contract: every log call here is structured and writes only operation
names, doc ids, durations, and translated error class names. Request bodies,
metadata, container tags, and search queries are never logged. Exceptions raised
by this module preserve the SDK exception via `__cause__`; do NOT log the cause
chain downstream — the SDK's exceptions can carry response payloads.
"""

from __future__ import annotations

import time
from typing import Any, NamedTuple, Protocol, cast
from uuid import UUID

import httpx
import structlog
from pydantic import SecretStr
from supermemory import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    Supermemory,
    omit,
)

from app.core.config import Settings, get_settings

log = structlog.get_logger(__name__)


# Single-user app: steady-state Supermemory traffic is one inline call per user
# action, so the pool naturally stays at 1-2 sockets. The explicit cap is
# defense-in-depth: if a future fan-out path (bulk re-sync, parallel search) is
# introduced accidentally, requests queue locally instead of stampeding the API.
_CONNECTION_LIMITS = httpx.Limits(
    max_connections=4,
    max_keepalive_connections=4,
    keepalive_expiry=5.0,
)


# Public metadata type for the Protocol. Kept narrow (no nested dicts, no None)
# to nudge callers toward simple, indexable shapes. The SDK's signature uses an
# almost-identical union but with a `SequenceNotStr[str]` alias that doesn't
# unify cleanly with `list[str]` under dict invariance — the adapter casts at
# the SDK boundary (see `add` / `patch`) rather than leaking the SDK type here.
MetadataValue = str | float | bool | list[str]
Metadata = dict[str, MetadataValue]


# ─── value types ───────────────────────────────────────────────────────────


class AddResult(NamedTuple):
    doc_id: str
    status: str


class SearchHit(NamedTuple):
    """A single search result.

    `doc_id` is Supermemory's internal `document_id`. The service hydrates
    journal-entry rows via `Memory.external_id IN (:doc_ids)`. Search responses
    do not currently echo `customId`; if a future API revision adds it, this
    type gains an optional field — no breaking change.
    """

    doc_id: str
    similarity: float


# ─── error hierarchy ───────────────────────────────────────────────────────


class MemoryClientError(Exception):
    """Base error for any backend failure."""


class MemoryClientAuthError(MemoryClientError):
    """401/403 — credential is wrong or lacks scope. Operator should alarm."""


class MemoryClientNotFoundError(MemoryClientError):
    """404 — referenced document does not exist."""


class MemoryClientRateLimitError(MemoryClientError):
    """429 — slow down."""


class MemoryClientPermanentError(MemoryClientError):
    """4xx caller bug (400/409/422 etc). Retry will not help; fix the request."""


class MemoryClientTransientError(MemoryClientError):
    """5xx, network, timeout — retry-eligible. Default for unmapped errors."""


# ─── Protocol ──────────────────────────────────────────────────────────────


class MemoryClient(Protocol):
    """Vendor-agnostic memory backend interface."""

    def add(
        self,
        *,
        custom_id: UUID,
        content: str,
        container_tags: list[str],
        metadata: Metadata,
        entity_context: str | None = None,
    ) -> AddResult: ...

    def patch(
        self,
        *,
        doc_id: str,
        content: str | None = None,
        metadata: Metadata | None = None,
        container_tags: list[str] | None = None,
    ) -> None: ...

    def delete(self, *, doc_id: str) -> None: ...

    def search(
        self,
        *,
        q: str,
        container_tag: str,
        limit: int = 10,
    ) -> list[SearchHit]: ...


# ─── concrete adapter ──────────────────────────────────────────────────────


def _translate(exc: BaseException) -> MemoryClientError:
    if isinstance(exc, AuthenticationError | PermissionDeniedError):
        return MemoryClientAuthError(type(exc).__name__)
    if isinstance(exc, NotFoundError):
        return MemoryClientNotFoundError(type(exc).__name__)
    if isinstance(exc, RateLimitError):
        return MemoryClientRateLimitError(type(exc).__name__)
    if isinstance(exc, APIStatusError) and 400 <= exc.status_code < 500:
        # 400/409/422 etc. — caller bug; retry will not help.
        return MemoryClientPermanentError(type(exc).__name__)
    if isinstance(exc, APIConnectionError | APITimeoutError | APIError):
        return MemoryClientTransientError(type(exc).__name__)
    return MemoryClientTransientError(type(exc).__name__)


class SupermemoryClient:
    """`MemoryClient` implementation backed by the official Supermemory SDK."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: SecretStr,
        timeout_seconds: float,
        sdk: Supermemory | None = None,
    ) -> None:
        self._sdk = sdk or Supermemory(
            api_key=api_key.get_secret_value(),
            base_url=base_url,
            timeout=timeout_seconds,
            max_retries=0,
            http_client=httpx.Client(limits=_CONNECTION_LIMITS),
        )

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> SupermemoryClient:
        if settings is None:
            settings = get_settings()
        return cls(
            base_url=settings.supermemory_base_url,
            api_key=settings.supermemory_api_key,
            timeout_seconds=settings.supermemory_timeout_ms / 1000,
        )

    def close(self) -> None:
        self._sdk.close()

    def add(
        self,
        *,
        custom_id: UUID,
        content: str,
        container_tags: list[str],
        metadata: Metadata,
        entity_context: str | None = None,
    ) -> AddResult:
        start = time.perf_counter()
        try:
            resp = self._sdk.documents.add(
                content=content,
                container_tags=container_tags,
                custom_id=str(custom_id),
                # SDK uses SequenceNotStr[str] in its union; cast localised here.
                metadata=cast("dict[str, Any]", metadata),
                entity_context=entity_context if entity_context is not None else omit,
            )
        except Exception as exc:
            err = _translate(exc)
            log.warning(
                "memory_client.add_err",
                error_class=type(err).__name__,
                duration_ms=int((time.perf_counter() - start) * 1000),
            )
            raise err from exc

        log.info(
            "memory_client.add_ok",
            doc_id=resp.id,
            status=resp.status,
            duration_ms=int((time.perf_counter() - start) * 1000),
        )
        return AddResult(doc_id=resp.id, status=resp.status)

    def patch(
        self,
        *,
        doc_id: str,
        content: str | None = None,
        metadata: Metadata | None = None,
        container_tags: list[str] | None = None,
    ) -> None:
        start = time.perf_counter()
        try:
            self._sdk.documents.update(
                doc_id,
                content=content if content is not None else omit,
                metadata=cast("dict[str, Any]", metadata) if metadata is not None else omit,
                container_tags=container_tags if container_tags is not None else omit,
            )
        except Exception as exc:
            err = _translate(exc)
            log.warning(
                "memory_client.patch_err",
                doc_id=doc_id,
                error_class=type(err).__name__,
                duration_ms=int((time.perf_counter() - start) * 1000),
            )
            raise err from exc

        log.info(
            "memory_client.patch_ok",
            doc_id=doc_id,
            duration_ms=int((time.perf_counter() - start) * 1000),
        )

    def delete(self, *, doc_id: str) -> None:
        start = time.perf_counter()
        try:
            self._sdk.documents.delete(doc_id)
        except NotFoundError:
            log.info(
                "memory_client.delete_ok",
                doc_id=doc_id,
                already_absent=True,
                duration_ms=int((time.perf_counter() - start) * 1000),
            )
            return
        except Exception as exc:
            err = _translate(exc)
            log.warning(
                "memory_client.delete_err",
                doc_id=doc_id,
                error_class=type(err).__name__,
                duration_ms=int((time.perf_counter() - start) * 1000),
            )
            raise err from exc

        log.info(
            "memory_client.delete_ok",
            doc_id=doc_id,
            duration_ms=int((time.perf_counter() - start) * 1000),
        )

    def search(
        self,
        *,
        q: str,
        container_tag: str,
        limit: int = 10,
    ) -> list[SearchHit]:
        start = time.perf_counter()
        try:
            resp = self._sdk.search.documents(
                q=q,
                container_tag=container_tag,
                limit=limit,
            )
        except Exception as exc:
            err = _translate(exc)
            log.warning(
                "memory_client.search_err",
                error_class=type(err).__name__,
                duration_ms=int((time.perf_counter() - start) * 1000),
            )
            raise err from exc

        hits = [
            SearchHit(doc_id=r.document_id, similarity=r.score)
            for r in resp.results
            if r.document_id
        ]
        log.info(
            "memory_client.search_ok",
            count=len(hits),
            duration_ms=int((time.perf_counter() - start) * 1000),
        )
        return hits
