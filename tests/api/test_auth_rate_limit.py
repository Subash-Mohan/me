"""Auth throttling integration tests.

Each test starts from a fresh DB so rate-limit state does not leak across
cases. The owner row is reseeded for every test because login and verify
both need the real passphrase path.
"""

import pytest
from fastapi.testclient import TestClient

from tests._db import reset_db, seed_owner

PHRASE = "phase-one-auth-throttle"


@pytest.fixture(autouse=True)
def _reset() -> None:
    reset_db()
    seed_owner(PHRASE)


def _login_token(client: TestClient) -> str:
    resp = client.post("/auth/login", json={"passphrase": PHRASE})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def test_login_locks_after_five_bad_attempts(client: TestClient) -> None:
    for _ in range(4):
        resp = client.post("/auth/login", json={"passphrase": "wrong phrase"})
        assert resp.status_code == 401
        assert resp.json() == {"detail": "invalid_credentials"}

    resp = client.post("/auth/login", json={"passphrase": "wrong phrase"})
    assert resp.status_code == 429
    assert resp.json() == {"detail": "too_many_attempts"}
    assert "Retry-After" in resp.headers


def test_login_success_clears_prior_failures(client: TestClient) -> None:
    for _ in range(2):
        resp = client.post("/auth/login", json={"passphrase": "wrong phrase"})
        assert resp.status_code == 401

    ok = client.post("/auth/login", json={"passphrase": PHRASE})
    assert ok.status_code == 200

    again = client.post("/auth/login", json={"passphrase": "wrong phrase"})
    assert again.status_code == 401
    assert again.json() == {"detail": "invalid_credentials"}


def test_verify_passphrase_locks_after_five_bad_attempts(client: TestClient) -> None:
    token = _login_token(client)
    headers = {"authorization": f"Bearer {token}"}

    for _ in range(4):
        resp = client.post(
            "/auth/verify-passphrase",
            json={"passphrase": "wrong phrase"},
            headers=headers,
        )
        assert resp.status_code == 401
        assert resp.json() == {"detail": "invalid_credentials"}

    resp = client.post(
        "/auth/verify-passphrase",
        json={"passphrase": "wrong phrase"},
        headers=headers,
    )
    assert resp.status_code == 429
    assert resp.json() == {"detail": "too_many_attempts"}
    assert "Retry-After" in resp.headers


def test_forwarded_header_is_ignored_by_default_for_login_buckets(client: TestClient) -> None:
    for i in range(4):
        resp = client.post(
            "/auth/login",
            json={"passphrase": "wrong phrase"},
            headers={"x-forwarded-for": f"203.0.113.{10 + i}"},
        )
        assert resp.status_code == 401

    resp = client.post(
        "/auth/login",
        json={"passphrase": "wrong phrase"},
        headers={"x-forwarded-for": "198.51.100.99"},
    )
    assert resp.status_code == 429
    assert resp.json() == {"detail": "too_many_attempts"}
