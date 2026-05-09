"""FastAPI dependency providers."""

from __future__ import annotations

from functools import lru_cache

from app.core.config import get_settings
from app.services.memory_client import MemoryClient, SupermemoryClient


@lru_cache(maxsize=1)
def _build_memory_client() -> SupermemoryClient:
    return SupermemoryClient.from_settings(get_settings())


def get_memory_client() -> MemoryClient:
    return _build_memory_client()


def shutdown_memory_client() -> None:
    """Close the singleton SDK client and clear the cache. Called from lifespan."""
    if _build_memory_client.cache_info().currsize == 0:
        return
    client = _build_memory_client()
    try:
        client.close()
    finally:
        _build_memory_client.cache_clear()
