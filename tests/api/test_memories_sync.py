"""POST /memories/{id}/sync — drives one row toward `external_status='synced'`."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.services.memory_client import AddResult, MemoryClientTransientError
from tests._db import reset_db, seed_extra_user, seed_memory, seed_owner
from tests._memory import auth_headers, owner_id
from tests._memory_client_fake import FakeMemoryClient

PHRASE = "sync-test-passphrase-blue-sky"


@pytest.fixture(autouse=True)
def _reset() -> None:
    reset_db()
    seed_owner(PHRASE)


def test_sync_unsynced_row_with_no_external_id_calls_add(
    client: TestClient, memory_client: FakeMemoryClient
) -> None:
    headers = auth_headers(client, PHRASE)
    owner = owner_id(client, headers)
    mid = seed_memory(user_id=owner, text_body="needs sync", external_status="unsynced")

    resp = client.post(f"/memories/{mid}/sync", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["external_status"] == "synced"
    assert body["external_id"] is not None
    assert any(op == "add" for op, _ in memory_client.calls)


def test_sync_unsynced_row_with_external_id_calls_patch(
    client: TestClient, memory_client: FakeMemoryClient
) -> None:
    headers = auth_headers(client, PHRASE)
    owner = owner_id(client, headers)
    # Seed the fake with a doc so patch() doesn't 404 in the fake.
    add: AddResult = memory_client.add(
        custom_id=uuid4(),
        content="seeded",
        container_tags=[],
        metadata={},
    )
    mid = seed_memory(
        user_id=owner,
        text_body="needs patch sync",
        external_status="unsynced",
        external_id=add.doc_id,
    )

    resp = client.post(f"/memories/{mid}/sync", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["external_status"] == "synced"
    assert any(op == "patch" for op, _ in memory_client.calls)


def test_sync_already_synced_is_noop(client: TestClient, memory_client: FakeMemoryClient) -> None:
    headers = auth_headers(client, PHRASE)
    owner = owner_id(client, headers)
    mid = seed_memory(
        user_id=owner,
        text_body="already synced",
        external_status="synced",
        external_id="doc_existing",
    )

    resp = client.post(f"/memories/{mid}/sync", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["external_status"] == "synced"
    # No client call when already synced.
    assert memory_client.calls == []


def test_sync_pending_delete_calls_delete(
    client: TestClient, memory_client: FakeMemoryClient
) -> None:
    headers = auth_headers(client, PHRASE)
    owner = owner_id(client, headers)
    mid = seed_memory(
        user_id=owner,
        text_body="pending del",
        external_status="pending_delete",
        external_id="doc_to_delete",
        deleted_at=datetime(2026, 5, 8, tzinfo=UTC),
    )

    resp = client.post(f"/memories/{mid}/sync", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["external_status"] == "synced"
    assert any(op == "delete" for op, _ in memory_client.calls)


def test_sync_after_fake_failure_records_external_error(
    client: TestClient, memory_client: FakeMemoryClient
) -> None:
    headers = auth_headers(client, PHRASE)
    owner = owner_id(client, headers)
    mid = seed_memory(user_id=owner, text_body="will fail", external_status="unsynced")
    memory_client.fail_next("add", error=MemoryClientTransientError("boom"))

    resp = client.post(f"/memories/{mid}/sync", headers=headers)
    # Service swallows the client error; HTTP response is still 200, row stays unsynced.
    assert resp.status_code == 200
    body = resp.json()
    assert body["external_status"] == "unsynced"
    assert body["external_error"] == "MemoryClientTransientError"


def test_sync_missing_returns_404(client: TestClient) -> None:
    headers = auth_headers(client, PHRASE)
    resp = client.post(f"/memories/{uuid4()}/sync", headers=headers)
    assert resp.status_code == 404


def test_sync_cross_user_returns_404(client: TestClient) -> None:
    headers = auth_headers(client, PHRASE)
    other = seed_extra_user("other-user-sync")
    mid = seed_memory(user_id=other, text_body="not yours", external_status="unsynced")

    resp = client.post(f"/memories/{mid}/sync", headers=headers)
    assert resp.status_code == 404
