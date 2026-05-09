"""In-memory `MemoryClient` test double.

Implements the `MemoryClient` Protocol structurally so service- and
endpoint-level tests can drive every code path without hitting Supermemory.
Failure-mode coverage uses `fail_next("op", error=...)` to queue a single
exception for the next call.
"""

from __future__ import annotations

from collections import deque
from uuid import UUID

from app.services.memory_client import (
    AddResult,
    MemoryClientError,
    MemoryClientNotFoundError,
    MemoryClientTransientError,
    Metadata,
    SearchHit,
)


class FakeMemoryClient:
    """Structural implementation of `MemoryClient` for tests."""

    def __init__(self) -> None:
        self.docs: dict[str, dict[str, object]] = {}
        self._search_results: list[SearchHit] = []
        self._failures: dict[str, deque[MemoryClientError]] = {
            "add": deque(),
            "patch": deque(),
            "delete": deque(),
            "search": deque(),
        }
        self.calls: list[tuple[str, dict[str, object]]] = []

    # ─── test-side controls ────────────────────────────────────────────

    def fail_next(
        self,
        op: str,
        *,
        error: MemoryClientError | None = None,
    ) -> None:
        """Queue an exception for the next call to `op`. Default error class is
        `MemoryClientTransientError`."""
        if op not in self._failures:
            raise ValueError(f"unknown op: {op!r}")
        self._failures[op].append(error or MemoryClientTransientError("fake failure"))

    def set_search_results(self, hits: list[SearchHit]) -> None:
        self._search_results = list(hits)

    # ─── MemoryClient surface ──────────────────────────────────────────

    def add(
        self,
        *,
        custom_id: UUID,
        content: str,
        container_tags: list[str],
        metadata: Metadata,
        entity_context: str | None = None,
    ) -> AddResult:
        self.calls.append(
            (
                "add",
                {
                    "custom_id": custom_id,
                    "content": content,
                    "container_tags": container_tags,
                    "metadata": metadata,
                    "entity_context": entity_context,
                },
            )
        )
        if self._failures["add"]:
            raise self._failures["add"].popleft()
        doc_id = "doc_" + custom_id.hex
        self.docs[doc_id] = {
            "custom_id": custom_id,
            "content": content,
            "container_tags": list(container_tags),
            "metadata": dict(metadata),
            "entity_context": entity_context,
        }
        return AddResult(doc_id=doc_id, status="queued")

    def patch(
        self,
        *,
        doc_id: str,
        content: str | None = None,
        metadata: Metadata | None = None,
        container_tags: list[str] | None = None,
    ) -> None:
        self.calls.append(
            (
                "patch",
                {
                    "doc_id": doc_id,
                    "content": content,
                    "metadata": metadata,
                    "container_tags": container_tags,
                },
            )
        )
        if self._failures["patch"]:
            raise self._failures["patch"].popleft()
        if doc_id not in self.docs:
            raise MemoryClientNotFoundError(doc_id)
        entry = self.docs[doc_id]
        if content is not None:
            entry["content"] = content
        if metadata is not None:
            entry["metadata"] = dict(metadata)
        if container_tags is not None:
            entry["container_tags"] = list(container_tags)

    def delete(self, *, doc_id: str) -> None:
        self.calls.append(("delete", {"doc_id": doc_id}))
        if self._failures["delete"]:
            raise self._failures["delete"].popleft()
        self.docs.pop(doc_id, None)

    def search(
        self,
        *,
        q: str,
        container_tag: str,
        limit: int = 10,
    ) -> list[SearchHit]:
        self.calls.append(("search", {"q": q, "container_tag": container_tag, "limit": limit}))
        if self._failures["search"]:
            raise self._failures["search"].popleft()
        return list(self._search_results[:limit])
