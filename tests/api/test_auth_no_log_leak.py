"""Verify the passphrase is never written to logs across any auth surface.

Module-scoped fixture seeds a single owner with a unique-string passphrase and
reconfigures logging at INFO so the auth events actually fire. Restored on teardown.
"""

from collections.abc import Iterator
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import confirm_passphrase
from app.db.session import get_db
from tests._db import reset_db, seed_owner

PHRASE = "uniqueteststring-bluesky-verysecret"


@pytest.fixture(scope="module", autouse=True)
def _setup() -> Iterator[None]:
    reset_db()
    seed_owner(PHRASE)

    import os

    prev_level = os.environ.get("LOG_LEVEL")
    os.environ["LOG_LEVEL"] = "INFO"
    from app.core.config import get_settings
    from app.core.logging import configure_logging

    get_settings.cache_clear()
    configure_logging(get_settings())
    yield
    if prev_level is None:
        os.environ.pop("LOG_LEVEL", None)
    else:
        os.environ["LOG_LEVEL"] = prev_level
    get_settings.cache_clear()
    configure_logging(get_settings())


def test_passphrase_not_logged_on_login_success(
    client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    capsys.readouterr()
    resp = client.post("/auth/login", json={"passphrase": PHRASE})
    assert resp.status_code == 200
    captured = capsys.readouterr()
    assert PHRASE not in captured.out
    assert PHRASE not in captured.err


def test_passphrase_not_logged_on_login_failure(
    client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    token = client.post("/auth/login", json={"passphrase": PHRASE}).json()["access_token"]
    capsys.readouterr()
    bad = client.post("/auth/login", json={"passphrase": "wrong-" + PHRASE})
    assert bad.status_code == 401
    captured = capsys.readouterr()
    assert PHRASE not in captured.out
    assert PHRASE not in captured.err
    assert token not in captured.out
    assert token not in captured.err


def test_passphrase_not_logged_on_verify_endpoint(
    client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    token = client.post("/auth/login", json={"passphrase": PHRASE}).json()["access_token"]
    capsys.readouterr()
    client.post(
        "/auth/verify-passphrase",
        json={"passphrase": "wrong-" + PHRASE},
        headers={"authorization": f"Bearer {token}"},
    )
    captured = capsys.readouterr()
    assert PHRASE not in captured.out
    assert PHRASE not in captured.err


def test_passphrase_not_logged_via_confirm_dep(
    db: Session, capsys: pytest.CaptureFixture[str]
) -> None:
    sub = FastAPI()

    @sub.delete("/p")
    def _(_: Annotated[None, Depends(confirm_passphrase)]) -> dict[str, str]:
        return {"ok": "yes"}

    def _override() -> object:
        yield db

    sub.dependency_overrides[get_db] = _override
    capsys.readouterr()

    sc = TestClient(sub)
    sc.delete("/p", headers={"x-confirm-passphrase": PHRASE})
    sc.delete("/p", headers={"x-confirm-passphrase": "wrong-" + PHRASE})
    captured = capsys.readouterr()
    assert PHRASE not in captured.out
    assert PHRASE not in captured.err
