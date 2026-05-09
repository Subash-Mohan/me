import os
from collections.abc import Iterator

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://me:me@localhost:5435/me_test")
os.environ.setdefault("ENV", "test")
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("JWT_SECRET", "x" * 32)
os.environ.setdefault("SUPERMEMORY_API_KEY", "test-key-not-real")
os.environ.setdefault("SUPERMEMORY_BASE_URL", "http://supermemory.test")
os.environ.setdefault("SUPERMEMORY_TIMEOUT_MS", "50")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests._memory_client_fake import FakeMemoryClient


@pytest.fixture
def db() -> Iterator[Session]:
    from app.db.session import SessionLocal

    with SessionLocal() as session:
        yield session


@pytest.fixture
def memory_client() -> Iterator[FakeMemoryClient]:
    from app.core.deps import get_memory_client
    from app.main import app

    fake = FakeMemoryClient()
    app.dependency_overrides[get_memory_client] = lambda: fake
    try:
        yield fake
    finally:
        app.dependency_overrides.pop(get_memory_client, None)


@pytest.fixture
def client(db: Session, memory_client: FakeMemoryClient) -> Iterator[TestClient]:
    from app.db.session import get_db
    from app.main import app

    def _override() -> Iterator[Session]:
        yield db

    app.dependency_overrides[get_db] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)
