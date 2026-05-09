"""Typed errors for the memory service.

Lives in its own module so `_memory_helpers.py` can raise them without
importing from `memory.py` (which in turn imports from `_memory_helpers`).
"""

from __future__ import annotations


class MemoryNotFound(KeyError):
    """The memory does not exist for this user, or has been soft-deleted."""


class MemoryDuplicate(ValueError):
    """Another non-deleted row already has the same (user_id, content_hash)."""


class MemoryValidationError(ValueError):
    """Caller-side validation failure (bad TZ, lat/lng pairing, etc.)."""


class MemoryIdempotencyReused(ValueError):
    """`idempotency_id` collides with an existing primary key (typically a
    soft-deleted row). Distinct from `MemoryDuplicate`, which signals a
    canonical-text collision."""
