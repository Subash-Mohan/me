from datetime import date as _date
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.db.session import SessionLocal, engine


def reset_db() -> None:
    """Truncate all app tables. Refuses to run against any DB whose name doesn't end in _test."""
    db_name = make_url(str(engine.url)).database
    assert db_name and db_name.endswith("_test"), (
        f"reset_db() refuses to run against {db_name!r} — DB name must end with _test"
    )
    with engine.begin() as conn:
        # Explicit per table — `users` cascades to `memories` via FK, but spelling
        # both out keeps the dependency direction obvious if FKs ever change.
        conn.execute(text("TRUNCATE TABLE memories CASCADE"))
        conn.execute(text("TRUNCATE TABLE users RESTART IDENTITY CASCADE"))


def seed_owner(passphrase: str = "test passphrase do not use") -> UUID:
    from app.services.owner import create_owner_user

    with SessionLocal() as session:
        user = create_owner_user(session, passphrase)
        session.commit()
        return user.id


def seed_extra_user(passphrase: str = "extra-user-passphrase") -> UUID:
    """Insert an additional `User` row directly, bypassing the single-owner guard.

    `create_owner_user` refuses to seed a second owner; cross-user isolation
    tests need a second `user_id` with a satisfied FK so memory rows for that
    user can be inserted via `seed_memory`.
    """
    from app.core.security import hash_passphrase
    from app.models.user import User

    with SessionLocal() as session:
        user = User(passphrase_hash=hash_passphrase(passphrase))
        session.add(user)
        session.commit()
        return user.id


def seed_memory(
    *,
    user_id: UUID,
    text_body: str = "seed entry",
    event_date: _date | None = None,
    **overrides: Any,
) -> UUID:
    """Insert a memory directly via the ORM and return its id.

    Bypasses the service layer so tests can construct rows with any
    `external_status` / `external_id` / `deleted_at` they need to exercise
    edge cases without going through `create_memory`. `overrides` are passed
    straight to the `Memory` constructor.
    """
    from app.models.memory import Memory
    from app.services._memory_helpers import canonical_hash

    if event_date is None:
        event_date = _date(2026, 5, 8)

    fields: dict[str, Any] = {
        "user_id": user_id,
        "text": text_body,
        "event_date": event_date,
        "event_tz": "UTC",
        "content_hash": canonical_hash(text_body),
    }
    fields.update(overrides)

    with SessionLocal() as session:
        memory = Memory(**fields)
        session.add(memory)
        session.commit()
        return memory.id
