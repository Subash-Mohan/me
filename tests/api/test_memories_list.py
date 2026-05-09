"""GET /memories — pagination, filters, cross-user isolation."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from tests._db import reset_db, seed_extra_user, seed_memory, seed_owner
from tests._memory import auth_headers, owner_id

PHRASE = "list-test-passphrase-blue-sky"


@pytest.fixture(autouse=True)
def _reset() -> None:
    reset_db()
    seed_owner(PHRASE)


def test_list_empty_returns_empty_items(client: TestClient) -> None:
    headers = auth_headers(client, PHRASE)
    resp = client.get("/memories", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {"items": [], "next_cursor": None}


def test_list_returns_descending_by_event_date(client: TestClient) -> None:
    headers = auth_headers(client, PHRASE)
    owner = owner_id(client, headers)
    seed_memory(user_id=owner, text_body="oldest", event_date=date(2026, 1, 1))
    seed_memory(user_id=owner, text_body="middle", event_date=date(2026, 3, 1))
    seed_memory(user_id=owner, text_body="newest", event_date=date(2026, 5, 1))

    resp = client.get("/memories", headers=headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert [i["text_preview"] for i in items] == ["newest", "middle", "oldest"]


def test_list_pagination_cursor_round_trips(client: TestClient) -> None:
    headers = auth_headers(client, PHRASE)
    owner = owner_id(client, headers)
    for i in range(5):
        seed_memory(user_id=owner, text_body=f"entry-{i}", event_date=date(2026, 5, 1 + i))

    page1 = client.get("/memories?limit=2", headers=headers).json()
    assert len(page1["items"]) == 2
    assert page1["next_cursor"] is not None

    page2 = client.get(f"/memories?limit=2&cursor={page1['next_cursor']}", headers=headers).json()
    assert len(page2["items"]) == 2
    assert page2["next_cursor"] is not None

    page1_ids = {i["id"] for i in page1["items"]}
    page2_ids = {i["id"] for i in page2["items"]}
    assert page1_ids.isdisjoint(page2_ids)


def test_list_date_range_filter(client: TestClient) -> None:
    headers = auth_headers(client, PHRASE)
    owner = owner_id(client, headers)
    seed_memory(user_id=owner, text_body="early", event_date=date(2026, 1, 1))
    seed_memory(user_id=owner, text_body="middle", event_date=date(2026, 3, 1))
    seed_memory(user_id=owner, text_body="late", event_date=date(2026, 5, 1))

    resp = client.get("/memories?from_date=2026-02-01&to_date=2026-04-01", headers=headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert [i["text_preview"] for i in items] == ["middle"]


def test_list_cross_user_isolation(client: TestClient) -> None:
    headers = auth_headers(client, PHRASE)
    owner = owner_id(client, headers)
    seed_memory(user_id=owner, text_body="mine", event_date=date(2026, 5, 1))

    other = seed_extra_user("other-user-9912")
    seed_memory(user_id=other, text_body="theirs", event_date=date(2026, 5, 2))

    resp = client.get("/memories", headers=headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert [i["text_preview"] for i in items] == ["mine"]


def test_list_malformed_cursor_returns_422(client: TestClient) -> None:
    headers = auth_headers(client, PHRASE)
    resp = client.get("/memories?cursor=not-a-real-cursor", headers=headers)
    assert resp.status_code == 422


def test_list_limit_out_of_range_returns_422(client: TestClient) -> None:
    headers = auth_headers(client, PHRASE)
    too_big = client.get("/memories?limit=999", headers=headers)
    assert too_big.status_code == 422
    too_small = client.get("/memories?limit=0", headers=headers)
    assert too_small.status_code == 422


def test_list_invalid_from_date_returns_422(client: TestClient) -> None:
    headers = auth_headers(client, PHRASE)
    resp = client.get("/memories?from_date=not-a-date", headers=headers)
    assert resp.status_code == 422
