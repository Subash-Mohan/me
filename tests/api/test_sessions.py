"""POST/GET/DELETE /sessions — happy path, isolation, pagination, soft delete."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.message import Message
from app.models.session import Session as SessionModel
from tests._db import (
    reset_db,
    seed_extra_user,
    seed_message,
    seed_owner,
    seed_session,
)
from tests._memory import auth_headers, owner_id

PHRASE = "sessions-test-phrase-violet-iron"


@pytest.fixture(autouse=True)
def _reset() -> None:
    reset_db()
    seed_owner(PHRASE)


def test_create_session_with_title(client: TestClient) -> None:
    headers = auth_headers(client, PHRASE)
    resp = client.post("/sessions", headers=headers, json={"title": "My first chat"})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["title"] == "My first chat"
    assert body["last_message_at"] is not None
    assert "id" in body


def test_create_session_without_title(client: TestClient) -> None:
    headers = auth_headers(client, PHRASE)
    resp = client.post("/sessions", headers=headers, json={})
    assert resp.status_code == 201
    assert resp.json()["title"] is None


def test_list_sessions_returns_only_callers(client: TestClient) -> None:
    headers = auth_headers(client, PHRASE)
    owner = owner_id(client, headers)
    mine = seed_session(user_id=owner, title="mine")

    other = seed_extra_user("other-phrase-9912")
    seed_session(user_id=other, title="theirs")

    resp = client.get("/sessions", headers=headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert [i["id"] for i in items] == [str(mine)]


def test_list_sessions_sorted_by_last_message_at_desc(client: TestClient) -> None:
    headers = auth_headers(client, PHRASE)
    owner = owner_id(client, headers)

    base = datetime.now(UTC)
    older = seed_session(user_id=owner, title="older", last_message_at=base - timedelta(hours=2))
    middle = seed_session(user_id=owner, title="middle", last_message_at=base - timedelta(hours=1))
    newest = seed_session(user_id=owner, title="newest", last_message_at=base)

    resp = client.get("/sessions", headers=headers)
    ids = [i["id"] for i in resp.json()["items"]]
    assert ids == [str(newest), str(middle), str(older)]


def test_list_sessions_pagination_cursor_round_trips(client: TestClient) -> None:
    headers = auth_headers(client, PHRASE)
    owner = owner_id(client, headers)
    base = datetime.now(UTC)
    for i in range(5):
        seed_session(
            user_id=owner,
            title=f"s{i}",
            last_message_at=base - timedelta(minutes=i),
        )

    page1 = client.get("/sessions?limit=2", headers=headers).json()
    assert len(page1["items"]) == 2
    assert page1["next_cursor"] is not None

    page2 = client.get(f"/sessions?limit=2&cursor={page1['next_cursor']}", headers=headers).json()
    assert len(page2["items"]) == 2

    page1_ids = {i["id"] for i in page1["items"]}
    page2_ids = {i["id"] for i in page2["items"]}
    assert page1_ids.isdisjoint(page2_ids)


def test_get_session_returns_messages_oldest_first(client: TestClient) -> None:
    headers = auth_headers(client, PHRASE)
    owner = owner_id(client, headers)
    session_id = seed_session(user_id=owner, title="t")

    base = datetime.now(UTC)
    seed_message(
        user_id=owner,
        session_id=session_id,
        role="user",
        content="hello",
        created_at=base - timedelta(seconds=10),
    )
    user_msg_id = seed_message(
        user_id=owner,
        session_id=session_id,
        role="user",
        content="follow-up",
        created_at=base - timedelta(seconds=5),
    )
    seed_message(
        user_id=owner,
        session_id=session_id,
        role="assistant",
        content="reply",
        parent_message_id=user_msg_id,
        created_at=base,
    )

    resp = client.get(f"/sessions/{session_id}", headers=headers)
    assert resp.status_code == 200
    contents = [m["content"] for m in resp.json()["messages"]]
    assert contents == ["hello", "follow-up", "reply"]


def test_get_session_404_for_other_users_session(client: TestClient) -> None:
    headers = auth_headers(client, PHRASE)
    other = seed_extra_user("other-phrase-1234")
    foreign = seed_session(user_id=other, title="not yours")

    resp = client.get(f"/sessions/{foreign}", headers=headers)
    assert resp.status_code == 404


def test_delete_session_soft_deletes_session_and_messages(client: TestClient, db: Session) -> None:
    headers = auth_headers(client, PHRASE)
    owner = owner_id(client, headers)
    session_id = seed_session(user_id=owner, title="doomed")
    seed_message(user_id=owner, session_id=session_id, role="user", content="bye")

    resp = client.delete(f"/sessions/{session_id}", headers=headers)
    assert resp.status_code == 204

    db.expire_all()
    s = db.get(SessionModel, session_id)
    assert s is not None
    assert s.deleted_at is not None

    surviving = (
        db.query(Message)
        .filter(Message.session_id == session_id, Message.deleted_at.is_(None))
        .count()
    )
    assert surviving == 0

    # Subsequent GET returns 404.
    resp2 = client.get(f"/sessions/{session_id}", headers=headers)
    assert resp2.status_code == 404


def test_delete_session_404_for_other_users_session(client: TestClient) -> None:
    headers = auth_headers(client, PHRASE)
    other = seed_extra_user("other-phrase-5678")
    foreign = seed_session(user_id=other, title="not yours")
    resp = client.delete(f"/sessions/{foreign}", headers=headers)
    assert resp.status_code == 404
