"""Auth-surface tests that run against an empty users table.

Module-scoped fixture truncates once at the top; tests must not seed any user.
"""

from datetime import timedelta
from typing import Annotated
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import confirm_passphrase, mint_access_token
from app.db.session import get_db
from tests._db import reset_db


@pytest.fixture(scope="module", autouse=True)
def _reset() -> None:
    reset_db()


def test_login_returns_401_when_no_user(client: TestClient) -> None:
    resp = client.post("/auth/login", json={"passphrase": "anything"})
    assert resp.status_code == 401
    assert resp.json() == {"detail": "invalid_credentials"}


def test_me_requires_authorization_header(client: TestClient) -> None:
    assert client.get("/auth/me").status_code == 401


def test_me_rejects_malformed_authorization_header(client: TestClient) -> None:
    resp = client.get("/auth/me", headers={"authorization": "NotBearer xxx"})
    assert resp.status_code == 401


def test_me_rejects_garbage_token(client: TestClient) -> None:
    resp = client.get("/auth/me", headers={"authorization": "Bearer garbage.token.here"})
    assert resp.status_code == 401


def test_me_rejects_token_signed_with_wrong_secret(client: TestClient) -> None:
    token, _ = mint_access_token(uuid4(), secret="z" * 32, expires_in=timedelta(days=30))
    resp = client.get("/auth/me", headers={"authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_verify_passphrase_no_jwt_returns_401(client: TestClient) -> None:
    resp = client.post("/auth/verify-passphrase", json={"passphrase": "anything"})
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


def test_confirm_passphrase_dep_missing_header_returns_401(db: Session) -> None:
    sc = _make_protected_client(db)
    assert sc.delete("/protected").status_code == 401


def test_confirm_passphrase_dep_no_user_in_db_returns_401(db: Session) -> None:
    sc = _make_protected_client(db)
    resp = sc.delete("/protected", headers={"x-confirm-passphrase": "any phrase"})
    assert resp.status_code == 401
