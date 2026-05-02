"""Tests for the create_owner_user service.

Module-scoped reset; tests run in source order, with state accumulating:
- empty-passphrase guard fires before any DB lookup, so it runs first against an empty DB
- the insert test then creates the owner row
- the duplicate test then asserts the next call raises
"""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import verify_passphrase
from app.models.user import User
from app.services.owner import (
    EmptyPassphraseError,
    OwnerAlreadyExistsError,
    create_owner_user,
)
from tests._db import reset_db

PHRASE = "blue sky cat unicycle"


@pytest.fixture(scope="module", autouse=True)
def _reset() -> None:
    reset_db()


def test_create_owner_user_raises_on_empty_passphrase(db: Session) -> None:
    with pytest.raises(EmptyPassphraseError):
        create_owner_user(db, "")


def test_create_owner_user_inserts_when_db_empty(db: Session) -> None:
    user = create_owner_user(db, PHRASE)
    db.commit()
    rows = db.execute(select(User)).scalars().all()
    assert len(rows) == 1
    assert rows[0].id == user.id
    assert rows[0].passphrase_hash.startswith("$argon2id$")
    assert verify_passphrase(PHRASE, rows[0].passphrase_hash)


def test_create_owner_user_raises_when_user_exists(db: Session) -> None:
    with pytest.raises(OwnerAlreadyExistsError):
        create_owner_user(db, "second phrase")
