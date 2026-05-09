"""Shared HTTP-side helpers for the `/memories` endpoint test suites.

Memory tests are JWT-authenticated and frequently need the authenticated
user's id; these two helpers cover both needs and are imported across the
eight `tests/api/test_memories_*.py` files.
"""

from __future__ import annotations

from uuid import UUID

from fastapi.testclient import TestClient


def auth_headers(client: TestClient, passphrase: str) -> dict[str, str]:
    """Mint a JWT via `/auth/login` and return the `Authorization` header dict."""
    resp = client.post("/auth/login", json={"passphrase": passphrase})
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"authorization": f"Bearer {token}"}


def owner_id(client: TestClient, headers: dict[str, str]) -> UUID:
    """Return the `id` of the JWT-bearing user via `GET /auth/me`."""
    return UUID(client.get("/auth/me", headers=headers).json()["id"])
