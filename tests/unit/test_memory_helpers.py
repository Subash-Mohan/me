"""Unit tests for `app.services._memory_helpers`. Pure functions; no DB."""

from __future__ import annotations

from datetime import date
from uuid import UUID, uuid4

import pytest

from app.services._memory_helpers import (
    canonical_hash,
    decode_cursor,
    encode_cursor,
    text_preview,
    validate_tz,
)
from app.services.memory import MemoryValidationError

# ─── canonical_hash ────────────────────────────────────────────────────────


def test_canonical_hash_returns_32_bytes() -> None:
    digest = canonical_hash("hello")
    assert isinstance(digest, bytes)
    assert len(digest) == 32


def test_canonical_hash_is_deterministic() -> None:
    assert canonical_hash("hello") == canonical_hash("hello")


def test_canonical_hash_strips_whitespace() -> None:
    assert canonical_hash("hello") == canonical_hash("  hello  ")


def test_canonical_hash_is_case_insensitive() -> None:
    assert canonical_hash("Hello") == canonical_hash("HELLO")


def test_canonical_hash_normalises_unicode_nfc() -> None:
    # "é" can be a precomposed char (U+00E9) or e + combining acute (U+0065 U+0301).
    nfc = "café"
    nfd = "café"
    assert nfc != nfd  # raw bytes differ
    assert canonical_hash(nfc) == canonical_hash(nfd)


def test_canonical_hash_distinguishes_different_text() -> None:
    assert canonical_hash("hello") != canonical_hash("world")


# ─── validate_tz ───────────────────────────────────────────────────────────


def test_validate_tz_returns_name_for_valid_zone() -> None:
    assert validate_tz("UTC") == "UTC"
    assert validate_tz("America/New_York") == "America/New_York"


def test_validate_tz_raises_on_unknown_zone() -> None:
    with pytest.raises(MemoryValidationError):
        validate_tz("Not/A/Zone")


def test_validate_tz_raises_on_empty_string() -> None:
    with pytest.raises(MemoryValidationError):
        validate_tz("")


# ─── cursor codec ──────────────────────────────────────────────────────────


def test_cursor_round_trip() -> None:
    d = date(2026, 5, 8)
    mid = uuid4()
    encoded = encode_cursor(d, mid)
    decoded_d, decoded_id = decode_cursor(encoded)
    assert decoded_d == d
    assert decoded_id == mid


def test_cursor_is_opaque_string() -> None:
    encoded = encode_cursor(date(2026, 5, 8), uuid4())
    assert isinstance(encoded, str)
    assert encoded != ""
    # No raw date/uuid leakage in the encoded form.
    assert "2026" not in encoded
    assert "-" not in encoded  # neither date hyphens nor uuid hyphens


def test_cursor_decode_raises_on_garbage() -> None:
    with pytest.raises(MemoryValidationError):
        decode_cursor("not-a-valid-cursor")


def test_cursor_decode_raises_on_unknown_version() -> None:
    import base64
    import json

    payload = json.dumps({"v": 999, "ed": "2026-05-08", "id": str(uuid4())}).encode()
    bogus = base64.urlsafe_b64encode(payload).decode().rstrip("=")
    with pytest.raises(MemoryValidationError):
        decode_cursor(bogus)


def test_cursor_decode_raises_on_missing_fields() -> None:
    import base64
    import json

    payload = json.dumps({"v": 1, "ed": "2026-05-08"}).encode()
    bogus = base64.urlsafe_b64encode(payload).decode().rstrip("=")
    with pytest.raises(MemoryValidationError):
        decode_cursor(bogus)


def test_cursor_decode_raises_on_bad_uuid() -> None:
    import base64
    import json

    payload = json.dumps({"v": 1, "ed": "2026-05-08", "id": "not-a-uuid"}).encode()
    bogus = base64.urlsafe_b64encode(payload).decode().rstrip("=")
    with pytest.raises(MemoryValidationError):
        decode_cursor(bogus)


def test_cursor_decode_raises_on_bad_date() -> None:
    import base64
    import json

    payload = json.dumps({"v": 1, "ed": "not-a-date", "id": str(uuid4())}).encode()
    bogus = base64.urlsafe_b64encode(payload).decode().rstrip("=")
    with pytest.raises(MemoryValidationError):
        decode_cursor(bogus)


# ─── text_preview ──────────────────────────────────────────────────────────


def test_text_preview_passes_short_text_through() -> None:
    assert text_preview("hello") == "hello"


def test_text_preview_truncates_long_text() -> None:
    long = "x" * 500
    out = text_preview(long, max_chars=200)
    assert len(out) == 200


def test_text_preview_default_max_is_200() -> None:
    out = text_preview("y" * 500)
    assert len(out) == 200


def test_text_preview_stops_at_first_blank_line() -> None:
    body = "first paragraph\n\nsecond paragraph that should not appear"
    out = text_preview(body)
    assert out == "first paragraph"


def test_text_preview_keeps_single_newlines() -> None:
    body = "line one\nline two\nline three"
    out = text_preview(body, max_chars=200)
    # Single newlines aren't paragraph breaks; stay in the preview.
    assert out == body


def test_text_preview_empty_string() -> None:
    assert text_preview("") == ""


# ─── helper imports stay private ───────────────────────────────────────────


def test_uuid_round_trip_uses_canonical_form() -> None:
    """Cursor decodes to a `UUID` object, not a string. Catches accidental str leakage."""
    mid = UUID("12345678-1234-5678-1234-567812345678")
    encoded = encode_cursor(date(2026, 5, 8), mid)
    _, decoded_id = decode_cursor(encoded)
    assert isinstance(decoded_id, UUID)
    assert decoded_id == mid
