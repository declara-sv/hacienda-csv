"""Password hashing, JWT access tokens and refresh tokens."""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import secrets
import uuid
from typing import Annotated

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

from app.api.errors import ApiError
from app.config import Settings

_password_hash = PasswordHash((Argon2Hasher(),))
_bearer = HTTPBearer(auto_error=False)

CLOCK_SKEW_SECONDS = 30
NAME_IDENTIFIER_CLAIM = "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier"


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hash.verify(password, password_hash)
    except Exception:
        return False


def create_access_token(
    *, user_id: uuid.UUID, email: str, full_name: str, settings: Settings
) -> tuple[str, dt.datetime]:
    now = dt.datetime.now(dt.UTC)
    expires_at = now + dt.timedelta(minutes=settings.jwt_access_token_minutes)
    claims = {
        "sub": str(user_id),
        NAME_IDENTIFIER_CLAIM: str(user_id),
        "email": email,
        "name": full_name,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "nbf": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    token = jwt.encode(claims, settings.jwt_signing_key, algorithm="HS256")
    return token, expires_at.replace(microsecond=0)


def decode_access_token(token: str, settings: Settings) -> uuid.UUID | None:
    try:
        claims = jwt.decode(
            token,
            settings.jwt_signing_key,
            algorithms=["HS256"],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            leeway=CLOCK_SKEW_SECONDS,
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
    except jwt.PyJWTError:
        return None
    try:
        return uuid.UUID(str(claims.get(NAME_IDENTIFIER_CLAIM) or claims["sub"]))
    except (KeyError, ValueError):
        return None


def generate_refresh_token() -> str:
    return base64.b64encode(secrets.token_bytes(64)).decode("ascii")


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest().upper()


def _unauthorized() -> ApiError:
    return ApiError(401, "No autorizado.", headers={"WWW-Authenticate": "Bearer"})


def get_current_user_id(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> uuid.UUID:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()
    user_id = decode_access_token(credentials.credentials, request.app.state.settings)
    if user_id is None:
        raise _unauthorized()
    return user_id


CurrentUserId = Annotated[uuid.UUID, Depends(get_current_user_id)]
