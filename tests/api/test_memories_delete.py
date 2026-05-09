"""DELETE /memories/{id} — soft-delete + step-up via X-Confirm-Passphrase."""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from tests._db import reset_db, seed_extra_user, seed_memory, seed_owner
from tests._memory import auth_headers, owner_id

PHRASE = "delete-test-passphrase-blue-sky"


@pytest.fixture(autouse=True)
def _reset() -> None:
    reset_db()
    seed_owner(PHRASE)


def test_delete_returns_204_and_hides_row(client: TestClient) -> None:
    headers = auth_headers(client, PHRASE)
    owner = owner_id(client, headers)
    mid = seed_memory(user_id=owner, text_body="to delete")

    resp = client.delete(
        f"/memories/{mid}",
        headers={**headers, "x-confirm-passphrase": PHRASE},
    )
    assert resp.status_code == 204
    assert resp.text == ""

    # Verify the row is now hidden from detail.
    detail = client.get(f"/memories/{mid}", headers=headers)
    assert detail.status_code == 404


def test_delete_idempotent_second_call_also_204(client: TestClient) -> None:
    headers = auth_headers(client, PHRASE)
    owner = owner_id(client, headers)
    mid = seed_memory(user_id=owner, text_body="delete me twice")

    full_headers = {**headers, "x-confirm-passphrase": PHRASE}
    first = client.delete(f"/memories/{mid}", headers=full_headers)
    second = client.delete(f"/memories/{mid}", headers=full_headers)
    assert first.status_code == 204
    assert second.status_code == 204


def test_delete_missing_passphrase_header_returns_401(client: TestClient) -> None:
    headers = auth_headers(client, PHRASE)
    owner = owner_id(client, headers)
    mid = seed_memory(user_id=owner, text_body="no header")

    resp = client.delete(f"/memories/{mid}", headers=headers)  # no x-confirm-passphrase
    assert resp.status_code == 401


def test_delete_wrong_passphrase_returns_401(client: TestClient) -> None:
    headers = auth_headers(client, PHRASE)
    owner = owner_id(client, headers)
    mid = seed_memory(user_id=owner, text_body="bad header")

    resp = client.delete(
        f"/memories/{mid}",
        headers={**headers, "x-confirm-passphrase": "wrong"},
    )
    assert resp.status_code == 401


def test_delete_cross_user_returns_404(client: TestClient) -> None:
    headers = auth_headers(client, PHRASE)
    # Share PHRASE so confirm_passphrase succeeds regardless of which user
    # `select(User).limit(1)` returns first — it can land on either row when
    # two users exist (Postgres scan order is undefined without ORDER BY).
    other = seed_extra_user(PHRASE)
    mid = seed_memory(user_id=other, text_body="not yours")

    resp = client.delete(
        f"/memories/{mid}",
        headers={**headers, "x-confirm-passphrase": PHRASE},
    )
    assert resp.status_code == 404


def test_delete_truly_missing_returns_404(client: TestClient) -> None:
    headers = auth_headers(client, PHRASE)
    resp = client.delete(
        f"/memories/{uuid4()}",
        headers={**headers, "x-confirm-passphrase": PHRASE},
    )
    assert resp.status_code == 404
