from datetime import timedelta
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import client_ip, current_user, mint_access_token, verify_passphrase
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, LoginResponse, MeResponse, VerifyPassphraseRequest

router = APIRouter(prefix="/auth", tags=["auth"])

log = structlog.get_logger(__name__)


_INVALID_CREDS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_credentials"
)


@router.post("/login", response_model=LoginResponse)
def login(
    body: LoginRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> LoginResponse:
    ip = client_ip(request)
    user = db.execute(select(User).limit(1)).scalar_one_or_none()
    if user is None or not verify_passphrase(body.passphrase, user.passphrase_hash):
        log.info("auth.login_fail", ip=ip)
        raise _INVALID_CREDS

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
def verify_passphrase_route(
    body: VerifyPassphraseRequest,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> Response:
    ip = client_ip(request)
    if not verify_passphrase(body.passphrase, user.passphrase_hash):
        log.info("auth.verify_fail", user_id=str(user.id), ip=ip)
        raise _INVALID_CREDS

    log.info("auth.verify_ok", user_id=str(user.id), ip=ip)
    return Response(status_code=204)
