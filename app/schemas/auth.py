from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class LoginRequest(BaseModel):
    passphrase: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    expires_at: datetime


class MeResponse(BaseModel):
    id: UUID
    created_at: datetime


class VerifyPassphraseRequest(BaseModel):
    passphrase: str
