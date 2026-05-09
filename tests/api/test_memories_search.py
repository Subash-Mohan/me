"""GET /memories/search — Supermemory primary, local FTS fallback."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.services.memory_client import SearchHit
from tests._db import reset_db, seed_memory, seed_owner
from tests._memory import auth_headers, owner_id
from tests._memory_client_fake import FakeMemoryClient

PHRASE = "search-test-passphrase-blue-sky"


@pytest.fixture(autouse=True)
def _reset() -> None:
    reset_db()
    seed_owner(PHRASE)


def test_search_supermemory_returns_hydrated_rows(
    client: TestClient, memory_client: FakeMemoryClient
) -> None:
    headers = auth_headers(client, PHRASE)
    owner = owner_id(client, headers)
    mid = seed_memory(user_id=owner, text_body="lunch with alex", external_id="doc_lunch")
    memory_client.set_search_results([SearchHit(doc_id="doc_lunch", similarity=0.92)])

    resp = client.get("/memories/search?q=lunch", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "supermemory"
    assert len(body["items"]) == 1
    assert body["items"][0]["memory"]["id"] == str(mid)
    assert body["items"][0]["similarity"] == pytest.approx(0.92)


def test_search_falls_back_to_local_when_client_fails(
    client: TestClient, memory_client: FakeMemoryClient
) -> None:
    headers = auth_headers(client, PHRASE)
    owner = owner_id(client, headers)
    seed_memory(user_id=owner, text_body="apple pie was great")
    seed_memory(user_id=owner, text_body="completely unrelated")

    memory_client.fail_next("search")

    resp = client.get("/memories/search?q=apple", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "local"
    assert len(body["items"]) == 1
    assert body["items"][0]["memory"]["text_preview"].startswith("apple pie")
    assert body["items"][0]["similarity"] is None


def test_search_drops_soft_deleted_supermemory_hits(
    client: TestClient, memory_client: FakeMemoryClient
) -> None:
    headers = auth_headers(client, PHRASE)
    owner = owner_id(client, headers)
    seed_memory(
        user_id=owner,
        text_body="tombstoned",
        external_id="doc_dead",
        deleted_at=datetime(2026, 5, 8, tzinfo=UTC),
    )
    memory_client.set_search_results([SearchHit(doc_id="doc_dead", similarity=0.95)])

    resp = client.get("/memories/search?q=anything", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "supermemory"
    assert body["items"] == []


def test_search_drops_soft_deleted_local_hits(
    client: TestClient, memory_client: FakeMemoryClient
) -> None:
    headers = auth_headers(client, PHRASE)
    owner = owner_id(client, headers)
    seed_memory(
        user_id=owner,
        text_body="apple pie tombstone",
        deleted_at=datetime(2026, 5, 8, tzinfo=UTC),
    )
    memory_client.fail_next("search")

    resp = client.get("/memories/search?q=apple", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "local"
    assert body["items"] == []


def test_search_empty_q_returns_422(client: TestClient) -> None:
    headers = auth_headers(client, PHRASE)
    resp = client.get("/memories/search?q=", headers=headers)
    assert resp.status_code == 422


def test_search_limit_out_of_range_returns_422(client: TestClient) -> None:
    headers = auth_headers(client, PHRASE)
    too_big = client.get("/memories/search?q=hi&limit=999", headers=headers)
    too_small = client.get("/memories/search?q=hi&limit=0", headers=headers)
    assert too_big.status_code == 422
    assert too_small.status_code == 422
