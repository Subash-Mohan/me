"""Pure helpers used by the memory service.

These are intentionally side-effect free so they can be exercised by fast unit
tests without a database or HTTP client.
"""

from __future__ import annotations

import base64
import hashlib
import json
import unicodedata
from datetime import date
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.services.memory import MemoryValidationError

_CURSOR_VERSION = 1


def canonical_hash(text: str) -> bytes:
    """Stable 32-byte SHA-256 over the entry's canonical form.

    Canonical form is NFC-normalised, surrounding whitespace stripped, and
    lowercased. The same logical entry produces the same digest regardless of
    cosmetic differences (precomposed vs combining accents, leading/trailing
    spaces, casing). This digest backs the partial-unique index used for
    layer-2 dedupe in `create_memory`.
    """
    normalised = unicodedata.normalize("NFC", text).strip().lower()
    return hashlib.sha256(normalised.encode("utf-8")).digest()


def validate_tz(name: str) -> str:
    """Echo `name` if it identifies a real IANA zone, else raise."""
    if not name:
        raise MemoryValidationError("event_tz cannot be empty")
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise MemoryValidationError(f"unknown timezone: {name!r}") from exc
    return name


def encode_cursor(event_date: date, memory_id: UUID) -> str:
    """Opaque base64 cursor for keyset pagination.

    Versioned (`v=1`) so the shape can evolve later without breaking
    outstanding cursors.
    """
    payload = json.dumps(
        {"v": _CURSOR_VERSION, "ed": event_date.isoformat(), "id": str(memory_id)},
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")


def decode_cursor(cursor: str) -> tuple[date, UUID]:
    """Inverse of `encode_cursor`. Raises `MemoryValidationError` on any
    malformed input or unknown version."""
    try:
        # Re-pad before decoding — `urlsafe_b64encode` strips trailing '='.
        padding = "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(cursor + padding)
        payload = json.loads(raw)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise MemoryValidationError("malformed cursor") from exc

    if not isinstance(payload, dict):
        raise MemoryValidationError("malformed cursor")
    if payload.get("v") != _CURSOR_VERSION:
        raise MemoryValidationError(f"unsupported cursor version: {payload.get('v')!r}")

    ed = payload.get("ed")
    mid = payload.get("id")
    if not isinstance(ed, str) or not isinstance(mid, str):
        raise MemoryValidationError("cursor missing fields")

    try:
        decoded_date = date.fromisoformat(ed)
        decoded_id = UUID(mid)
    except ValueError as exc:
        raise MemoryValidationError("cursor field could not be parsed") from exc

    return decoded_date, decoded_id


def text_preview(text: str, *, max_chars: int = 200) -> str:
    """Compact list-view preview: first paragraph, capped at `max_chars`."""
    if not text:
        return ""
    # First blank-line-separated paragraph. `split` returns at least one element.
    head = text.split("\n\n", 1)[0]
    if len(head) > max_chars:
        return head[:max_chars]
    return head
