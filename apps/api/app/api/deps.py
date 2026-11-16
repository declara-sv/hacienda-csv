from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app.config import Settings
from app.security import CurrentUserId
from app.services.accounts import ACCOUNT_HEADER, AccountContext, resolve_account
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


def get_current_account(
    session: DbSession,
    user_id: CurrentUserId,
    x_account_id: Annotated[str | None, Header(alias=ACCOUNT_HEADER)] = None,
) -> AccountContext:
    return resolve_account(session, user_id, x_account_id)


CurrentAccount = Annotated[AccountContext, Depends(get_current_account)]
