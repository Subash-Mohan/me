"""Unit tests for the `SupermemoryClient` adapter.

Verify that the SDK's exception taxonomy is translated to the
`MemoryClient*Error` hierarchy, that the `Authorization: Bearer` header is sent,
that response shapes are mapped correctly, and that no request bodies, search
queries, container tags, or response payloads are written to logs.

Logging note: structlog writes via `PrintLoggerFactory` straight to stdout,
not through stdlib `logging` — so log assertions use `capsys`, not `caplog`,
matching the pattern in `tests/api/test_auth_no_log_leak.py`. The autouse
fixture below reconfigures logging at INFO for the duration of this module so
that INFO-level events actually emit (the default `LOG_LEVEL=WARNING` in
conftest would suppress them).
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from uuid import uuid4

import pytest
from pydantic import SecretStr
from pytest_httpx import HTTPXMock

from app.services.memory_client import (
    AddResult,
    MemoryClientAuthError,
    MemoryClientNotFoundError,
    MemoryClientPermanentError,
    MemoryClientRateLimitError,
    MemoryClientTransientError,
    SupermemoryClient,
)

BASE = "http://supermemory.test"
DOC_PATH = re.compile(rf"^{re.escape(BASE)}/v3/documents(/.*)?$")
SEARCH_DOCS_PATH = f"{BASE}/v3/search"


@pytest.fixture(scope="module", autouse=True)
def _info_logging() -> Iterator[None]:
    from app.core.config import get_settings
    from app.core.logging import configure_logging

    prev = os.environ.get("LOG_LEVEL")
    os.environ["LOG_LEVEL"] = "INFO"
    get_settings.cache_clear()
    configure_logging(get_settings())
    yield
    if prev is None:
        os.environ.pop("LOG_LEVEL", None)
    else:
        os.environ["LOG_LEVEL"] = prev
    get_settings.cache_clear()
    configure_logging(get_settings())


@pytest.fixture
def adapter() -> Iterator[SupermemoryClient]:
    client = SupermemoryClient(
        base_url=BASE,
        api_key=SecretStr("test-key-not-real"),
        timeout_seconds=2.0,
    )
    try:
        yield client
    finally:
        client.close()


# ─── add() ────────────────────────────────────────────────────────────────


def test_add_happy_path_returns_mapped_add_result(
    adapter: SupermemoryClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(
        url=f"{BASE}/v3/documents",
        method="POST",
        json={"id": "doc_abc123", "status": "queued"},
    )

    result = adapter.add(
        custom_id=uuid4(),
        content="hello",
        container_tags=["user_x"],
        metadata={"k": "v"},
    )

    assert result == AddResult(doc_id="doc_abc123", status="queued")


def test_add_sends_bearer_auth_header(adapter: SupermemoryClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=f"{BASE}/v3/documents",
        method="POST",
        json={"id": "doc_abc", "status": "queued"},
    )

    adapter.add(
        custom_id=uuid4(),
        content="x",
        container_tags=["user_x"],
        metadata={},
    )

    request = httpx_mock.get_request()
    assert request is not None
    assert request.headers["authorization"] == "Bearer test-key-not-real"


def test_add_401_raises_auth_error(adapter: SupermemoryClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=f"{BASE}/v3/documents",
        method="POST",
        status_code=401,
        json={"error": "unauthorized"},
    )

    with pytest.raises(MemoryClientAuthError):
        adapter.add(
            custom_id=uuid4(),
            content="x",
            container_tags=["user_x"],
            metadata={},
        )


def test_add_403_raises_auth_error(adapter: SupermemoryClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=f"{BASE}/v3/documents",
        method="POST",
        status_code=403,
        json={"error": "forbidden"},
    )

    with pytest.raises(MemoryClientAuthError):
        adapter.add(
            custom_id=uuid4(),
            content="x",
            container_tags=["user_x"],
            metadata={},
        )


def test_add_429_raises_rate_limit_error(adapter: SupermemoryClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=f"{BASE}/v3/documents",
        method="POST",
        status_code=429,
        json={"error": "rate limited"},
    )

    with pytest.raises(MemoryClientRateLimitError):
        adapter.add(
            custom_id=uuid4(),
            content="x",
            container_tags=["user_x"],
            metadata={},
        )


def test_add_503_raises_transient_error(adapter: SupermemoryClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=f"{BASE}/v3/documents",
        method="POST",
        status_code=503,
        json={"error": "unavailable"},
    )

    with pytest.raises(MemoryClientTransientError):
        adapter.add(
            custom_id=uuid4(),
            content="x",
            container_tags=["user_x"],
            metadata={},
        )


# ─── delete() ─────────────────────────────────────────────────────────────


def test_delete_happy_path(adapter: SupermemoryClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=f"{BASE}/v3/documents/doc_abc",
        method="DELETE",
        status_code=200,
        json={},
    )

    adapter.delete(doc_id="doc_abc")


def test_delete_404_is_silently_idempotent(
    adapter: SupermemoryClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(
        url=f"{BASE}/v3/documents/doc_missing",
        method="DELETE",
        status_code=404,
        json={"error": "not found"},
    )

    # No exception — idempotent. Verification §2 of 05c codifies the actual
    # response code; this test pins our adapter behavior to "404 → swallow".
    adapter.delete(doc_id="doc_missing")


def test_delete_503_raises_transient(adapter: SupermemoryClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=f"{BASE}/v3/documents/doc_abc",
        method="DELETE",
        status_code=503,
        json={"error": "unavailable"},
    )

    with pytest.raises(MemoryClientTransientError):
        adapter.delete(doc_id="doc_abc")


# ─── patch() ──────────────────────────────────────────────────────────────


def test_patch_happy_path(adapter: SupermemoryClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=f"{BASE}/v3/documents/doc_abc",
        method="PATCH",
        status_code=200,
        json={"id": "doc_abc", "status": "queued"},
    )

    adapter.patch(doc_id="doc_abc", content="new")


def test_patch_404_raises_not_found(adapter: SupermemoryClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=f"{BASE}/v3/documents/doc_missing",
        method="PATCH",
        status_code=404,
        json={"error": "not found"},
    )

    with pytest.raises(MemoryClientNotFoundError):
        adapter.patch(doc_id="doc_missing", content="x")


# ─── search() ─────────────────────────────────────────────────────────────


def test_search_maps_results_to_search_hits(
    adapter: SupermemoryClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(
        url=SEARCH_DOCS_PATH,
        method="POST",
        json={
            "results": [
                {
                    "documentId": "doc_a",
                    "score": 0.91,
                    "chunks": [],
                    "createdAt": "2026-05-09T00:00:00Z",
                    "updatedAt": "2026-05-09T00:00:00Z",
                },
                {
                    "documentId": "doc_b",
                    "score": 0.42,
                    "chunks": [],
                    "createdAt": "2026-05-09T00:00:00Z",
                    "updatedAt": "2026-05-09T00:00:00Z",
                },
            ],
            "timing": 12.0,
            "total": 2,
        },
    )

    hits = adapter.search(q="anything", container_tag="user_x", limit=10)

    assert [(h.doc_id, h.similarity) for h in hits] == [
        ("doc_a", 0.91),
        ("doc_b", 0.42),
    ]


def test_search_empty_results(adapter: SupermemoryClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=SEARCH_DOCS_PATH,
        method="POST",
        json={"results": [], "timing": 1.0, "total": 0},
    )

    assert adapter.search(q="ping", container_tag="user_x") == []


def test_search_5xx_raises_transient(adapter: SupermemoryClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=SEARCH_DOCS_PATH,
        method="POST",
        status_code=503,
        json={"error": "unavailable"},
    )

    with pytest.raises(MemoryClientTransientError):
        adapter.search(q="anything", container_tag="user_x")


# ─── privacy: no log leak ────────────────────────────────────────────────


def test_no_log_leak_on_add_error(
    adapter: SupermemoryClient,
    httpx_mock: HTTPXMock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    httpx_mock.add_response(
        url=f"{BASE}/v3/documents",
        method="POST",
        status_code=503,
        json={"error": "boom"},
    )

    secret_text = "extremely-private-journal-entry"
    secret_tag = "user_supersecretuserid"
    capsys.readouterr()
    with pytest.raises(MemoryClientTransientError):
        adapter.add(
            custom_id=uuid4(),
            content=secret_text,
            container_tags=[secret_tag],
            metadata={"location_label": "private-place"},
        )

    captured = capsys.readouterr()
    blob = captured.out + captured.err
    assert secret_text not in blob
    assert secret_tag not in blob
    assert "private-place" not in blob


def test_no_log_leak_on_search(
    adapter: SupermemoryClient,
    httpx_mock: HTTPXMock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    httpx_mock.add_response(
        url=SEARCH_DOCS_PATH,
        method="POST",
        json={"results": [], "timing": 1.0, "total": 0},
    )

    secret_q = "what-was-i-thinking-on-tuesday"
    secret_tag = "user_supersecretuserid"
    capsys.readouterr()
    adapter.search(q=secret_q, container_tag=secret_tag)

    captured = capsys.readouterr()
    blob = captured.out + captured.err
    assert secret_q not in blob
    assert secret_tag not in blob


# ─── 4xx caller errors → MemoryClientPermanentError ──────────────────────


@pytest.mark.parametrize("status_code", [400, 409, 422])
def test_add_4xx_caller_error_raises_permanent(
    adapter: SupermemoryClient,
    httpx_mock: HTTPXMock,
    status_code: int,
) -> None:
    httpx_mock.add_response(
        url=f"{BASE}/v3/documents",
        method="POST",
        status_code=status_code,
        json={"error": "caller bug"},
    )

    with pytest.raises(MemoryClientPermanentError):
        adapter.add(
            custom_id=uuid4(),
            content="x",
            container_tags=["user_x"],
            metadata={},
        )


# ─── entity_context routing ──────────────────────────────────────────────


def test_add_includes_entity_context_when_provided(
    adapter: SupermemoryClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(
        url=f"{BASE}/v3/documents",
        method="POST",
        json={"id": "doc_a", "status": "queued"},
    )

    adapter.add(
        custom_id=uuid4(),
        content="x",
        container_tags=["user_x"],
        metadata={},
        entity_context="journal-entity-context",
    )

    body = httpx_mock.get_request().read().decode()
    assert "entityContext" in body
    assert "journal-entity-context" in body


def test_add_omits_entity_context_when_not_provided(
    adapter: SupermemoryClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(
        url=f"{BASE}/v3/documents",
        method="POST",
        json={"id": "doc_a", "status": "queued"},
    )

    adapter.add(
        custom_id=uuid4(),
        content="x",
        container_tags=["user_x"],
        metadata={},
    )

    body = httpx_mock.get_request().read().decode()
    assert "entityContext" not in body


# ─── auth header is sent on every operation ─────────────────────────────


def test_patch_sends_bearer_auth_header(adapter: SupermemoryClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=f"{BASE}/v3/documents/doc_abc",
        method="PATCH",
        json={"id": "doc_abc", "status": "queued"},
    )

    adapter.patch(doc_id="doc_abc", content="x")

    request = httpx_mock.get_request()
    assert request.headers["authorization"] == "Bearer test-key-not-real"


def test_delete_sends_bearer_auth_header(adapter: SupermemoryClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=f"{BASE}/v3/documents/doc_abc",
        method="DELETE",
        json={},
    )

    adapter.delete(doc_id="doc_abc")

    request = httpx_mock.get_request()
    assert request.headers["authorization"] == "Bearer test-key-not-real"


def test_search_sends_bearer_auth_header(adapter: SupermemoryClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=SEARCH_DOCS_PATH,
        method="POST",
        json={"results": [], "timing": 1.0, "total": 0},
    )

    adapter.search(q="anything", container_tag="user_x")

    request = httpx_mock.get_request()
    assert request.headers["authorization"] == "Bearer test-key-not-real"


# ─── delete-404 idempotent path is logged correctly ─────────────────────


def test_delete_404_logs_already_absent(
    adapter: SupermemoryClient,
    httpx_mock: HTTPXMock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    httpx_mock.add_response(
        url=f"{BASE}/v3/documents/doc_missing",
        method="DELETE",
        status_code=404,
        json={"error": "not found"},
    )

    capsys.readouterr()
    adapter.delete(doc_id="doc_missing")

    captured = capsys.readouterr()
    blob = captured.out + captured.err
    # The event name + already_absent flag together prove we noticed the 404
    # and treated it as idempotent rather than the 200/204 happy path.
    assert "delete_ok" in blob
    assert "already_absent" in blob
