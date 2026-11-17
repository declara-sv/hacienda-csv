from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import User
from app.security import CurrentIdentity
from app.services.accounts import ACCOUNT_HEADER, AccountContext, resolve_account
from app.services.users import provision_user
from app.storage import FileStorage


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_session(request: Request) -> Iterator[Session]:
    session: Session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


def get_storage(request: Request) -> FileStorage:
    return request.app.state.storage


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
DbSession = Annotated[Session, Depends(get_session)]
StorageDep = Annotated[FileStorage, Depends(get_storage)]


def get_current_user(session: DbSession, identity: CurrentIdentity) -> User:
    """The local user behind the Clerk session token, provisioned on first request."""
    return provision_user(session, identity)


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_current_user_id(user: CurrentUser) -> uuid.UUID:
    return user.id


CurrentUserId = Annotated[uuid.UUID, Depends(get_current_user_id)]


def get_current_account(
    session: DbSession,
    user_id: CurrentUserId,
    x_account_id: Annotated[str | None, Header(alias=ACCOUNT_HEADER)] = None,
) -> AccountContext:
    return resolve_account(session, user_id, x_account_id)


CurrentAccount = Annotated[AccountContext, Depends(get_current_account)]
