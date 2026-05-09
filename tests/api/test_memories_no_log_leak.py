"""Verify no sensitive content reaches logs across any memory surface.

The custom capture: structlog uses `PrintLoggerFactory`, which builds a
`PrintLogger` for each emit (with `cache_logger_on_first_use=False`). Each
`PrintLogger` reads `sys.stdout` at construction, so swapping `sys.stdout`
inside the test reliably captures every structlog write — `capsys` does
not, because the standard-logging `StreamHandler` was bound to a different
stdout reference at `configure_logging` time.

httpx logs full URLs (including query strings) via stdlib logging; that is a
test-transport artifact, not production behaviour. We silence the `httpx`
logger so the assertion measures *our* surfaces only.
"""

from __future__ import annotations

import io
import logging
import os
import sys
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.services.memory_client import SearchHit
from tests._db import reset_db, seed_owner
from tests._memory import auth_headers
from tests._memory_client_fake import FakeMemoryClient

PHRASE = "noleak-test-passphrase-uniquestring"
SECRET_TEXT = "secret journal entry uniquestring-tango"
SECRET_LABEL = "42 Whisper Ln uniquestring-foxtrot"
SECRET_QUERY = "uniquestring-secret-query"


@pytest.fixture(scope="module", autouse=True)
def _setup() -> Iterator[None]:
    reset_db()
    seed_owner(PHRASE)

    prev_level = os.environ.get("LOG_LEVEL")
    os.environ["LOG_LEVEL"] = "INFO"
    from app.core.config import get_settings
    from app.core.logging import configure_logging

    get_settings.cache_clear()
    configure_logging(get_settings())
    yield
    if prev_level is None:
        os.environ.pop("LOG_LEVEL", None)
    else:
        os.environ["LOG_LEVEL"] = prev_level
    get_settings.cache_clear()
    configure_logging(get_settings())


@pytest.fixture(autouse=True)
def _reset_per_test() -> None:
    reset_db()
    seed_owner(PHRASE)


def test_no_leak_across_every_endpoint(
    client: TestClient,
    memory_client: FakeMemoryClient,
) -> None:
    # Silence httpx — the test transport logs full URLs including query
    # strings, which is a test artifact rather than production behaviour.
    logging.getLogger("httpx").setLevel(logging.WARNING)

    # Capture both pipelines:
    # - structlog → PrintLogger.write → sys.stdout (swapped here).
    # - stdlib logging → StreamHandler → its captured stdout (swapped via the
    #   handler's .stream attribute).
    buf = io.StringIO()
    real_stdout = sys.stdout
    sys.stdout = buf
    swapped_handlers: list[tuple[logging.StreamHandler, object]] = []
    for h in logging.getLogger().handlers:
        if isinstance(h, logging.StreamHandler):
            swapped_handlers.append((h, h.stream))
            h.stream = buf
    try:
        headers = auth_headers(client, PHRASE)
        create = client.post(
            "/memories",
            headers=headers,
            json={
                "text": SECRET_TEXT,
                "event_date": "2026-05-08",
                "event_tz": "UTC",
                "location_label": SECRET_LABEL,
            },
        )
        assert create.status_code == 201
        mid = create.json()["id"]
        external_id = create.json()["external_id"]

        client.get("/memories", headers=headers)
        client.get(f"/memories/{mid}", headers=headers)

        memory_client.set_search_results([SearchHit(doc_id=external_id, similarity=0.9)])
        client.get(f"/memories/search?q={SECRET_QUERY}", headers=headers)

        memory_client.fail_next("search")
        client.get(f"/memories/search?q={SECRET_QUERY}", headers=headers)

        client.patch(
            f"/memories/{mid}",
            headers=headers,
            json={"text": SECRET_TEXT + " edited", "location_label": SECRET_LABEL + " v2"},
        )
        client.post(f"/memories/{mid}/sync", headers=headers)
        client.delete(
            f"/memories/{mid}",
            headers={**headers, "x-confirm-passphrase": PHRASE},
        )
    finally:
        sys.stdout = real_stdout
        for h, prev_stream in swapped_handlers:
            h.stream = prev_stream

    captured = buf.getvalue()

    # Sanity: the buffer caught at least one application event. If this
    # assertion fails, the test would otherwise pass vacuously and we'd be
    # unable to distinguish "no leak" from "no logs at all".
    assert "auth.login_ok" in captured, "buffer caught no app events — test would be vacuous"

    for piece in (SECRET_TEXT, SECRET_LABEL, SECRET_QUERY, PHRASE):
        assert piece not in captured, f"sensitive content leaked into logs: {piece!r}"
