import os
from collections.abc import Iterator

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://me:me@localhost:5434/me_test")
os.environ.setdefault("ENV", "test")
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("JWT_SECRET", "x" * 32)

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


@pytest.fixture
def db() -> Iterator[Session]:
    from app.db.session import SessionLocal

    with SessionLocal() as session:
        yield session


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    from app.db.session import get_db
    from app.main import app

    def _override() -> Iterator[Session]:
        yield db

    app.dependency_overrides[get_db] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
