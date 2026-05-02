"""Tests for the `me` CLI.

Module-scoped reset; tests run in source order:
- DB-state-independent guards first (empty-passphrase, mismatched-prompt)
- then the arg-mode insert (creates the owner)
- then the duplicate-fail (depends on the prior insert)

The interactive prompt happy-path is unit-tested separately in
tests/unit/test_cli_prompt.py — keeping it out of here avoids creating a
second owner that would conflict with the prior insert.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cli import main
from app.models.user import User
from tests._db import reset_db

PHRASE = "blue sky cat unicycle"


@pytest.fixture(scope="module", autouse=True)
def _reset() -> None:
    reset_db()


def test_returns_2_on_empty_passphrase(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["create-owner", ""]) == 2
    captured = capsys.readouterr()
    assert "empty" in captured.err.lower()


def test_returns_2_on_mismatched_prompt(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs = iter(["one", "two"])
    monkeypatch.setattr("getpass.getpass", lambda _prompt="": next(inputs))
    with pytest.raises(SystemExit) as exc_info:
        main(["create-owner"])
    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "do not match" in captured.err.lower()


def test_inserts_user_via_arg(db: Session, capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["create-owner", PHRASE])
    assert rc == 0
    captured = capsys.readouterr()
    assert "Owner created:" in captured.out
    rows = db.execute(select(User)).scalars().all()
    assert len(rows) == 1


def test_returns_1_when_owner_already_exists(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["create-owner", "second phrase"])
    assert rc == 1
    captured = capsys.readouterr()
    assert "already exists" in captured.err
