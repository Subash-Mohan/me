"""GET /memories/{id} — happy path and 404 cases."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from tests._db import reset_db, seed_extra_user, seed_memory, seed_owner
from tests._memory import auth_headers, owner_id

PHRASE = "detail-test-passphrase-blue-sky"


@pytest.fixture(autouse=True)
def _reset() -> None:
    reset_db()
    seed_owner(PHRASE)


def test_detail_returns_full_row(client: TestClient) -> None:
    headers = auth_headers(client, PHRASE)
    owner = owner_id(client, headers)
    mid = seed_memory(user_id=owner, text_body="hello detail")

    resp = client.get(f"/memories/{mid}", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(mid)
    assert body["text"] == "hello detail"
    assert "external_status" in body
    assert "created_at" in body


def test_detail_missing_returns_404(client: TestClient) -> None:
    headers = auth_headers(client, PHRASE)
    resp = client.get(f"/memories/{uuid4()}", headers=headers)
    assert resp.status_code == 404


def test_detail_soft_deleted_returns_404(client: TestClient) -> None:
    headers = auth_headers(client, PHRASE)
    owner = owner_id(client, headers)
    mid = seed_memory(
        user_id=owner,
        text_body="tombstone",
        deleted_at=datetime(2026, 5, 8, tzinfo=UTC),
    )
    resp = client.get(f"/memories/{mid}", headers=headers)
    assert resp.status_code == 404


def test_detail_cross_user_returns_404(client: TestClient) -> None:
    headers = auth_headers(client, PHRASE)
    other = seed_extra_user("other-user-detail")
    mid = seed_memory(user_id=other, text_body="not yours")

    resp = client.get(f"/memories/{mid}", headers=headers)
    assert resp.status_code == 404
