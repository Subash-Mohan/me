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
        conn.execute(text("TRUNCATE TABLE users RESTART IDENTITY CASCADE"))


def seed_owner(passphrase: str = "test passphrase do not use") -> None:
    from app.services.owner import create_owner_user

    with SessionLocal() as session:
        create_owner_user(session, passphrase)
        session.commit()
