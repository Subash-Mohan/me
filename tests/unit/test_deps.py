"""Tests for `app/core/deps.py` — the FastAPI dependency providers.

Specifically guards against a regression where `_build_memory_client(settings)`
took an unhashable Pydantic `Settings` argument and crashed `lru_cache` on the
first real call. The fix is a parameterless factory.
"""

from __future__ import annotations

import pytest

from app.core.deps import (
    _build_memory_client,
    get_memory_client,
    shutdown_memory_client,
)
from app.services.memory_client import SupermemoryClient


@pytest.fixture(autouse=True)
def _isolate_singleton() -> None:
    _build_memory_client.cache_clear()
    yield
    _build_memory_client.cache_clear()


def test_get_memory_client_returns_supermemory_client() -> None:
    client = get_memory_client()
    assert isinstance(client, SupermemoryClient)
    # Sanity: the four MemoryClient methods exist (structural Protocol check).
    for op in ("add", "patch", "delete", "search"):
        assert callable(getattr(client, op))


def test_get_memory_client_returns_singleton() -> None:
    a = get_memory_client()
    b = get_memory_client()
    assert a is b


def test_shutdown_when_cache_empty_is_a_noop() -> None:
    # Pre-condition: cache is empty (the autouse fixture cleared it).
    assert _build_memory_client.cache_info().currsize == 0
    shutdown_memory_client()  # should not raise, should not build a client
    assert _build_memory_client.cache_info().currsize == 0


def test_shutdown_closes_and_clears_cache() -> None:
    client = get_memory_client()
    assert _build_memory_client.cache_info().currsize == 1

    shutdown_memory_client()
    assert _build_memory_client.cache_info().currsize == 0

    # After shutdown, get_memory_client builds a fresh instance.
    fresh = get_memory_client()
    assert fresh is not client
