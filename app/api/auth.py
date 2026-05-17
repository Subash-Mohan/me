from datetime import UTC, datetime, timedelta
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import (
    client_ip,
    current_user,
    mint_access_token,
)
from app.core.security import (
    verify_passphrase as check_passphrase,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, LoginResponse, MeResponse, VerifyPassphraseRequest
from app.services.auth_throttle import clear_failures, get_lock_expiry, record_failure

router = APIRouter(prefix="/auth", tags=["auth"])

log = structlog.get_logger(__name__)


_INVALID_CREDS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_credentials"
)


def _too_many_attempts(*, locked_until, now) -> HTTPException:
    retry_after = max(1, int((locked_until - now).total_seconds()))
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="too_many_attempts",
        headers={"Retry-After": str(retry_after)},
    )


@router.post("/login", response_model=LoginResponse)
def login(
    body: LoginRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> LoginResponse:
    now = datetime.now(UTC)
    ip = client_ip(request, settings)
    locked_until = get_lock_expiry(db, action="login", client_ip=ip, now=now)
    if locked_until is not None:
        raise _too_many_attempts(locked_until=locked_until, now=now)

    user = db.execute(select(User).limit(1)).scalar_one_or_none()
    if user is None or not check_passphrase(body.passphrase, user.passphrase_hash):
        locked_until = record_failure(db, action="login", client_ip=ip, now=now, settings=settings)
        log.info("auth.login_fail", ip=ip)
        if locked_until is not None:
            raise _too_many_attempts(locked_until=locked_until, now=now)
        raise _INVALID_CREDS

    clear_failures(db, action="login", client_ip=ip)
    token, expires_at = mint_access_token(
        user.id,
        secret=settings.jwt_secret.get_secret_value(),
        expires_in=timedelta(days=settings.jwt_expires_days),
    )
    log.info("auth.login_ok", user_id=str(user.id), ip=ip)
    return LoginResponse(access_token=token, token_type="bearer", expires_at=expires_at)


@router.get("/me", response_model=MeResponse)
def me(user: Annotated[User, Depends(current_user)]) -> MeResponse:
    return MeResponse(id=user.id, created_at=user.created_at)


@router.post("/verify-passphrase", status_code=204)
def verify_passphrase(
    body: VerifyPassphraseRequest,
    request: Request,
    user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    now = datetime.now(UTC)
    ip = client_ip(request, settings)
    locked_until = get_lock_expiry(db, action="verify_passphrase", client_ip=ip, now=now)
    if locked_until is not None:
        raise _too_many_attempts(locked_until=locked_until, now=now)

    if not check_passphrase(body.passphrase, user.passphrase_hash):
        locked_until = record_failure(
            db,
            action="verify_passphrase",
            client_ip=ip,
            now=now,
            settings=settings,
        )
        log.info("auth.verify_fail", user_id=str(user.id), ip=ip)
        if locked_until is not None:
            raise _too_many_attempts(locked_until=locked_until, now=now)
        raise _INVALID_CREDS

    clear_failures(db, action="verify_passphrase", client_ip=ip)
    log.info("auth.verify_ok", user_id=str(user.id), ip=ip)
    return Response(status_code=204)
