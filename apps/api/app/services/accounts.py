"""Accounts (accounting firms) and the current-account resolution used to scope every resource."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.errors import ApiError, validation_error
from app.models import Account, AccountMember, AccountRole, User

ACCOUNT_HEADER = "X-Account-Id"
NO_ACCOUNT = "El usuario no pertenece a ninguna cuenta."
FORBIDDEN_ACCOUNT = "No tiene acceso a esta cuenta."


@dataclass(frozen=True)
class AccountContext:
    """The authenticated user and the account the request acts on."""

    user_id: uuid.UUID
    account_id: uuid.UUID


@dataclass(frozen=True)
class Membership:
    account: Account
    role: str


def create_personal_account(session: Session, user: User) -> Account:
    """Account named after the user, with the user as Owner. Added to the session, not committed."""
    account = Account(name=user.full_name)
    session.add(account)
    session.flush()
    session.add(AccountMember(account_id=account.id, user_id=user.id, role=AccountRole.OWNER.value))
    return account


def _memberships_query(user_id: uuid.UUID):
    return (
        select(Account, AccountMember.role)
        .join(AccountMember, AccountMember.account_id == Account.id)
        .where(AccountMember.user_id == user_id)
        .order_by(AccountMember.created_at_utc, AccountMember.id)
    )


def default_membership(session: Session, user_id: uuid.UUID) -> Membership | None:
    """The user's earliest membership (a user has exactly one for now)."""
    row = session.execute(_memberships_query(user_id).limit(1)).first()
    return Membership(row[0], row[1]) if row is not None else None


def resolve_account(session: Session, user_id: uuid.UUID, requested: str | None) -> AccountContext:
    """The `X-Account-Id` header account when sent (must be a membership), else the default one."""
    if requested is not None and requested.strip():
        try:
            account_id = uuid.UUID(requested.strip())
        except ValueError as exc:
            raise validation_error(ACCOUNT_HEADER, "Identificador inválido.") from exc
        member = session.scalar(
            select(AccountMember.id).where(
                AccountMember.account_id == account_id, AccountMember.user_id == user_id
            )
        )
        if member is None:
            raise ApiError(403, FORBIDDEN_ACCOUNT)
        return AccountContext(user_id=user_id, account_id=account_id)

    membership = default_membership(session, user_id)
    if membership is None:
        raise ApiError(403, NO_ACCOUNT)
    return AccountContext(user_id=user_id, account_id=membership.account.id)
