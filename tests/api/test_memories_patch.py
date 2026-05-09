"""PATCH /memories/{id} — field updates, collisions, validation, 404s."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from tests._db import reset_db, seed_extra_user, seed_memory, seed_owner
from tests._memory import auth_headers, owner_id

PHRASE = "patch-test-passphrase-blue-sky"


@pytest.fixture(autouse=True)
def _reset() -> None:
    reset_db()
    seed_owner(PHRASE)


def test_patch_text_updates_field(client: TestClient) -> None:
    headers = auth_headers(client, PHRASE)
    owner = owner_id(client, headers)
    mid = seed_memory(user_id=owner, text_body="original")

    resp = client.patch(f"/memories/{mid}", headers=headers, json={"text": "edited"})
    assert resp.status_code == 200
    assert resp.json()["text"] == "edited"


def test_patch_event_date_updates_field(client: TestClient) -> None:
    headers = auth_headers(client, PHRASE)
    owner = owner_id(client, headers)
    mid = seed_memory(user_id=owner, text_body="for date patch")

    resp = client.patch(f"/memories/{mid}", headers=headers, json={"event_date": "2026-12-31"})
    assert resp.status_code == 200
    assert resp.json()["event_date"] == "2026-12-31"


def test_patch_location_label_updates_field(client: TestClient) -> None:
    headers = auth_headers(client, PHRASE)
    owner = owner_id(client, headers)
    mid = seed_memory(user_id=owner, text_body="for label patch")

    resp = client.patch(f"/memories/{mid}", headers=headers, json={"location_label": "Coffee Shop"})
    assert resp.status_code == 200
    assert resp.json()["location_label"] == "Coffee Shop"


def test_patch_omitted_field_preserves_existing(client: TestClient) -> None:
    headers = auth_headers(client, PHRASE)
    owner = owner_id(client, headers)
    mid = seed_memory(
        user_id=owner,
        text_body="keep me",
        location_label="Original Label",
    )

    # Patch only `text`; location_label must not be cleared.
    resp = client.patch(f"/memories/{mid}", headers=headers, json={"text": "edited"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["text"] == "edited"
    assert body["location_label"] == "Original Label"


def test_patch_text_collides_with_live_sibling_returns_409(client: TestClient) -> None:
    headers = auth_headers(client, PHRASE)
    owner = owner_id(client, headers)
    seed_memory(user_id=owner, text_body="taken text")
    other_id = seed_memory(user_id=owner, text_body="some other text")

    resp = client.patch(f"/memories/{other_id}", headers=headers, json={"text": "taken text"})
    assert resp.status_code == 409


def test_patch_text_matches_soft_deleted_sibling_succeeds(client: TestClient) -> None:
    # Partial unique index excludes deleted rows, so this should succeed.
    headers = auth_headers(client, PHRASE)
    owner = owner_id(client, headers)
    seed_memory(
        user_id=owner,
        text_body="reusable text",
        deleted_at=datetime(2026, 5, 8, tzinfo=UTC),
    )
    live_id = seed_memory(user_id=owner, text_body="some other text")

    resp = client.patch(f"/memories/{live_id}", headers=headers, json={"text": "reusable text"})
    assert resp.status_code == 200
    assert resp.json()["text"] == "reusable text"


def test_patch_invalid_tz_returns_422(client: TestClient) -> None:
    headers = auth_headers(client, PHRASE)
    owner = owner_id(client, headers)
    mid = seed_memory(user_id=owner, text_body="for tz patch")

    resp = client.patch(f"/memories/{mid}", headers=headers, json={"event_tz": "Atlantis/Pearl"})
    assert resp.status_code == 422


@pytest.mark.parametrize("field", ["text", "event_date", "event_tz"])
def test_patch_explicit_null_for_non_nullable_field_returns_422(
    client: TestClient, field: str
) -> None:
    headers = auth_headers(client, PHRASE)
    owner = owner_id(client, headers)
    mid = seed_memory(user_id=owner, text_body="for null patch")

    resp = client.patch(f"/memories/{mid}", headers=headers, json={field: None})
    assert resp.status_code == 422


def test_patch_missing_returns_404(client: TestClient) -> None:
    headers = auth_headers(client, PHRASE)
    resp = client.patch(f"/memories/{uuid4()}", headers=headers, json={"text": "anything"})
    assert resp.status_code == 404


def test_patch_soft_deleted_returns_404(client: TestClient) -> None:
    headers = auth_headers(client, PHRASE)
    owner = owner_id(client, headers)
    mid = seed_memory(
        user_id=owner,
        text_body="tombstone",
        deleted_at=datetime(2026, 5, 8, tzinfo=UTC),
    )
    resp = client.patch(f"/memories/{mid}", headers=headers, json={"text": "edit"})
    assert resp.status_code == 404


def test_patch_cross_user_returns_404(client: TestClient) -> None:
    headers = auth_headers(client, PHRASE)
    other = seed_extra_user("other-user-patch")
    mid = seed_memory(user_id=other, text_body="not yours")

    resp = client.patch(f"/memories/{mid}", headers=headers, json={"text": "edited"})
    assert resp.status_code == 404
