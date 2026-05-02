from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models.user import User

_hasher = PasswordHasher()

_JWT_ALGORITHM = "HS256"


class InvalidTokenError(Exception):
    pass


def hash_passphrase(plain: str) -> str:
    return _hasher.hash(plain)


def verify_passphrase(plain: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, plain)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def mint_access_token(user_id: UUID, *, secret: str, expires_in: timedelta) -> tuple[str, datetime]:
    now = datetime.now(UTC)
    expires_at = now + expires_in
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    token = jwt.encode(payload, secret, algorithm=_JWT_ALGORITHM)
    return token, expires_at


def decode_access_token(token: str, *, secret: str) -> UUID:
    try:
        payload = jwt.decode(token, secret, algorithms=[_JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(str(exc)) from exc
    sub = payload.get("sub")
    if not isinstance(sub, str):
        raise InvalidTokenError("token missing sub claim")
    try:
        return UUID(sub)
    except ValueError as exc:
        raise InvalidTokenError("token sub is not a uuid") from exc


_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="invalid_credentials",
)


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def bearer_token(request: Request) -> str:
    header = request.headers.get("authorization")
    if not header:
        raise _UNAUTHORIZED
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise _UNAUTHORIZED
    return token


def current_user(
    token: Annotated[str, Depends(bearer_token)],
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> User:
    try:
        user_id = decode_access_token(token, secret=settings.jwt_secret.get_secret_value())
    except InvalidTokenError as exc:
        raise _UNAUTHORIZED from exc
    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if user is None:
        raise _UNAUTHORIZED
    return user


def confirm_passphrase(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    supplied = request.headers.get("x-confirm-passphrase")
    if not supplied:
        raise _UNAUTHORIZED
    user = db.execute(select(User).limit(1)).scalar_one_or_none()
    if user is None or not verify_passphrase(supplied, user.passphrase_hash):
        raise _UNAUTHORIZED
