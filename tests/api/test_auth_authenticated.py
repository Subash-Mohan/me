"""Auth-surface tests that share a single seeded owner row.

Module-scoped fixture truncates and seeds once at the top.
"""

from datetime import UTC, datetime
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import confirm_passphrase
from app.db.session import get_db
from tests._db import reset_db, seed_owner

PHRASE = "blue sky cat unicycle"


@pytest.fixture(scope="module", autouse=True)
def _setup() -> None:
    reset_db()
    seed_owner(PHRASE)


def _login(client: TestClient) -> str:
    resp = client.post("/auth/login", json={"passphrase": PHRASE})
    assert resp.status_code == 200
    return resp.json()["access_token"]


# ---------- /auth/login ----------


def test_login_happy_path(client: TestClient) -> None:
    resp = client.post("/auth/login", json={"passphrase": PHRASE})
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert isinstance(body["access_token"], str)
    assert body["access_token"].count(".") == 2
    assert datetime.fromisoformat(body["expires_at"]) > datetime.now(UTC)


def test_login_wrong_passphrase_returns_401(client: TestClient) -> None:
    resp = client.post("/auth/login", json={"passphrase": "totally wrong"})
    assert resp.status_code == 401
    assert resp.json() == {"detail": "invalid_credentials"}


def test_login_missing_passphrase_returns_422(client: TestClient) -> None:
    assert client.post("/auth/login", json={}).status_code == 422


def test_login_response_does_not_echo_passphrase(client: TestClient) -> None:
    resp = client.post("/auth/login", json={"passphrase": PHRASE})
    assert PHRASE not in resp.text


# ---------- /auth/me ----------


def test_me_returns_user_shape_when_token_valid(client: TestClient) -> None:
    token = _login(client)
    resp = client.get("/auth/me", headers={"authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"id", "created_at"}
    assert len(body["id"]) == 36 and body["id"].count("-") == 4


# ---------- /auth/verify-passphrase ----------


def test_verify_passphrase_correct_returns_204(client: TestClient) -> None:
    token = _login(client)
    resp = client.post(
        "/auth/verify-passphrase",
        json={"passphrase": PHRASE},
        headers={"authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204
    assert resp.text == ""


def test_verify_passphrase_wrong_returns_401(client: TestClient) -> None:
    token = _login(client)
    resp = client.post(
        "/auth/verify-passphrase",
        json={"passphrase": "wrong phrase"},
        headers={"authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 401


# ---------- confirm_passphrase dep ----------


def _make_protected_client(db: Session) -> TestClient:
    sub = FastAPI()

    @sub.delete("/protected")
    def _(_: Annotated[None, Depends(confirm_passphrase)]) -> dict[str, str]:
        return {"deleted": "yes"}

    def _override() -> object:
        yield db

    sub.dependency_overrides[get_db] = _override
    return TestClient(sub)


def test_confirm_passphrase_dep_correct_header(db: Session) -> None:
    sc = _make_protected_client(db)
    resp = sc.delete("/protected", headers={"x-confirm-passphrase": PHRASE})
    assert resp.status_code == 200
    assert resp.json() == {"deleted": "yes"}


def test_confirm_passphrase_dep_wrong_header(db: Session) -> None:
    sc = _make_protected_client(db)
    resp = sc.delete("/protected", headers={"x-confirm-passphrase": "nope"})
    assert resp.status_code == 401
