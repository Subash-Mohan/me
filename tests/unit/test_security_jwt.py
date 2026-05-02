from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.core.security import (
    InvalidTokenError,
    decode_access_token,
    mint_access_token,
)


def test_mint_returns_token_and_future_expiry() -> None:
    user_id = uuid4()
    token, expires_at = mint_access_token(user_id, secret="x" * 32, expires_in=timedelta(days=30))
    assert isinstance(token, str)
    assert token.count(".") == 2  # header.payload.signature
    assert expires_at > datetime.now(UTC)
    assert expires_at < datetime.now(UTC) + timedelta(days=31)


def test_decode_round_trip_returns_user_id() -> None:
    user_id = uuid4()
    token, _ = mint_access_token(user_id, secret="x" * 32, expires_in=timedelta(days=30))
    assert decode_access_token(token, secret="x" * 32) == user_id


def test_decode_rejects_garbage() -> None:
    with pytest.raises(InvalidTokenError):
        decode_access_token("not.a.token", secret="x" * 32)


def test_decode_rejects_random_string() -> None:
    with pytest.raises(InvalidTokenError):
        decode_access_token("totally-bogus", secret="x" * 32)


def test_decode_rejects_wrong_secret() -> None:
    user_id = uuid4()
    token, _ = mint_access_token(user_id, secret="a" * 32, expires_in=timedelta(days=30))
    with pytest.raises(InvalidTokenError):
        decode_access_token(token, secret="b" * 32)


def test_decode_rejects_expired() -> None:
    user_id = uuid4()
    token, _ = mint_access_token(user_id, secret="x" * 32, expires_in=timedelta(seconds=-1))
    with pytest.raises(InvalidTokenError):
        decode_access_token(token, secret="x" * 32)
