from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Response, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import DbSession, SettingsDep
from app.api.errors import ApiError, validation_error
from app.api.schemas import AuthResponseDto, AuthUserDto, LoginRequest, RefreshRequest, RegisterRequest
from app.config import Settings
from app.models import RefreshToken, User
from app.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

INVALID_CREDENTIALS = "Credenciales inválidas."
INVALID_REFRESH = "Refresh token inválido o expirado."


def _unauthorized(message: str) -> ApiError:
    # `message` kept for clients of the previous API, `title` for ProblemDetails consumers.
    return ApiError(401, message, message=message)


def create_token_pair(session: Session, user: User, settings: Settings) -> AuthResponseDto:
    now = dt.datetime.now(dt.UTC)
    access_token, expires_at = create_access_token(
        user_id=user.id, email=user.email, full_name=user.full_name, settings=settings
    )
    refresh_token = generate_refresh_token()
    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(refresh_token),
            created_at_utc=now,
            expires_at_utc=now + dt.timedelta(days=settings.jwt_refresh_token_days),
        )
    )
    session.commit()
    return AuthResponseDto(
        access_token=access_token,
        access_token_expires_at_utc=expires_at,
        refresh_token=refresh_token,
        user=AuthUserDto(id=user.id, email=user.email, full_name=user.full_name),
    )


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(request: RegisterRequest, session: DbSession, settings: SettingsDep) -> AuthResponseDto:
    normalized = request.email.strip().lower()
    if session.scalar(select(User.id).where(User.normalized_email == normalized)) is not None:
        raise validation_error("email", "Este correo ya está registrado.")

    user = User(
        email=request.email.strip(),
        normalized_email=normalized,
        full_name=request.full_name.strip(),
        password_hash=hash_password(request.password),
    )
    session.add(user)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise validation_error("email", "Este correo ya está registrado.") from exc
    return create_token_pair(session, user, settings)


@router.post("/login")
def login(request: LoginRequest, session: DbSession, settings: SettingsDep) -> AuthResponseDto:
    normalized = request.email.strip().lower()
    user = session.scalar(select(User).where(User.normalized_email == normalized))
    if user is None or not verify_password(request.password, user.password_hash):
        raise _unauthorized(INVALID_CREDENTIALS)
    return create_token_pair(session, user, settings)


@router.post("/refresh")
def refresh(request: RefreshRequest, session: DbSession, settings: SettingsDep) -> AuthResponseDto:
    now = dt.datetime.now(dt.UTC)
    # Single statement so a token can be rotated only once even under concurrent requests.
    user_id = session.execute(
        update(RefreshToken)
        .where(
            RefreshToken.token_hash == hash_refresh_token(request.refresh_token),
            RefreshToken.revoked_at_utc.is_(None),
            RefreshToken.expires_at_utc > now,
        )
        .values(revoked_at_utc=now)
        .returning(RefreshToken.user_id)
    ).scalar_one_or_none()
    if user_id is None:
        session.rollback()
        raise _unauthorized(INVALID_REFRESH)

    user = session.get(User, user_id)
    if user is None:
        session.rollback()
        raise _unauthorized(INVALID_REFRESH)
    return create_token_pair(session, user, settings)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: RefreshRequest, session: DbSession) -> Response:
    session.execute(
        update(RefreshToken)
        .where(
            RefreshToken.token_hash == hash_refresh_token(request.refresh_token),
            RefreshToken.revoked_at_utc.is_(None),
        )
        .values(revoked_at_utc=dt.datetime.now(dt.UTC))
    )
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
