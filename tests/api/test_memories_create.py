"""POST /memories — happy path, validation, and idempotency."""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from tests._db import reset_db, seed_owner
from tests._memory import auth_headers
from tests._memory_client_fake import FakeMemoryClient

PHRASE = "create-test-passphrase-blue-sky"


@pytest.fixture(autouse=True)
def _reset() -> None:
    # Memory tests mutate rows; reset between every test so they don't leak.
    reset_db()
    seed_owner(PHRASE)


def test_create_returns_201_with_detail(
    client: TestClient, memory_client: FakeMemoryClient
) -> None:
    headers = auth_headers(client, PHRASE)
    resp = client.post(
        "/memories",
        headers=headers,
        json={"text": "first entry", "event_date": "2026-05-08", "event_tz": "UTC"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["text"] == "first entry"
    assert body["event_date"] == "2026-05-08"
    assert body["event_tz"] == "UTC"
    assert body["external_status"] == "synced"
    assert body["external_id"] is not None
    # The fake records the call with the user-scoped container tag.
    assert any(op == "add" for op, _ in memory_client.calls)


def test_create_without_token_returns_401(client: TestClient) -> None:
    resp = client.post(
        "/memories",
        json={"text": "no auth", "event_date": "2026-05-08", "event_tz": "UTC"},
    )
    assert resp.status_code == 401


def test_create_missing_text_returns_422(client: TestClient) -> None:
    headers = auth_headers(client, PHRASE)
    resp = client.post(
        "/memories",
        headers=headers,
        json={"event_date": "2026-05-08", "event_tz": "UTC"},
    )
    assert resp.status_code == 422


def test_create_invalid_tz_returns_422(client: TestClient) -> None:
    headers = auth_headers(client, PHRASE)
    resp = client.post(
        "/memories",
        headers=headers,
        json={"text": "bad tz", "event_date": "2026-05-08", "event_tz": "Mars/Phobos"},
    )
    assert resp.status_code == 422


def test_create_idempotent_same_id_returns_same_row(client: TestClient) -> None:
    headers = auth_headers(client, PHRASE)
    idem = str(uuid4())
    payload = {
        "text": "idempotent entry",
        "event_date": "2026-05-08",
        "event_tz": "UTC",
        "idempotency_id": idem,
    }
    first = client.post("/memories", headers=headers, json=payload)
    second = client.post("/memories", headers=headers, json=payload)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]


def test_create_dedupe_layer2_same_text_returns_same_row(client: TestClient) -> None:
    headers = auth_headers(client, PHRASE)
    payload_a = {
        "text": "duplicate text",
        "event_date": "2026-05-08",
        "event_tz": "UTC",
        "idempotency_id": str(uuid4()),
    }
    payload_b = {
        "text": "duplicate text",  # same canonical text
        "event_date": "2026-05-09",  # different date — still dedupes on text
        "event_tz": "UTC",
        "idempotency_id": str(uuid4()),  # different idempotency id
    }
    first = client.post("/memories", headers=headers, json=payload_a)
    second = client.post("/memories", headers=headers, json=payload_b)
    assert first.status_code == 201
    assert second.status_code == 201
    # Layer-2 dedupe is silent — never 409.
    assert first.json()["id"] == second.json()["id"]


def test_create_idempotency_reused_after_delete_returns_409(
    client: TestClient,
) -> None:
    headers = auth_headers(client, PHRASE)
    idem = str(uuid4())
    created = client.post(
        "/memories",
        headers=headers,
        json={
            "text": "will be deleted",
            "event_date": "2026-05-08",
            "event_tz": "UTC",
            "idempotency_id": idem,
        },
    )
    assert created.status_code == 201
    deleted = client.delete(
        f"/memories/{created.json()['id']}",
        headers={**headers, "x-confirm-passphrase": PHRASE},
    )
    assert deleted.status_code == 204

    # Reusing the idempotency id after a tombstone — service raises
    # MemoryIdempotencyReused → 409.
    reused = client.post(
        "/memories",
        headers=headers,
        json={
            "text": "different text",
            "event_date": "2026-05-08",
            "event_tz": "UTC",
            "idempotency_id": idem,
        },
    )
    assert reused.status_code == 409
