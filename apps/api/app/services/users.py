"""Just-in-time provisioning of users from verified Clerk identities."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import User
from app.security import ClerkIdentity
from app.services.accounts import create_personal_account

DEFAULT_FULL_NAME = "Usuario"
EMAIL_MAX = 320
NAME_MAX = 200


def _email(identity: ClerkIdentity) -> str | None:
    return identity.email[:EMAIL_MAX] if identity.email else None


def _name(identity: ClerkIdentity) -> str | None:
    return identity.name[:NAME_MAX] if identity.name else None


def _by_clerk_id(session: Session, clerk_user_id: str) -> User | None:
    return session.scalar(select(User).where(User.clerk_user_id == clerk_user_id))


def _create(session: Session, identity: ClerkIdentity) -> User | None:
    """User, personal account and Owner membership in one transaction. None if another request won."""
    email = _email(identity)
    user = User(
        clerk_user_id=identity.clerk_user_id,
        email=email,
        full_name=_name(identity) or (email[:NAME_MAX] if email else DEFAULT_FULL_NAME),
    )
    session.add(user)
    try:
        # The unique index on clerk_user_id makes a concurrent first request block here and then
        # fail once the winner commits, before any account row is written.
        session.flush()
        create_personal_account(session, user)
        session.commit()
    except IntegrityError:
        session.rollback()
        return None
    return user


def _sync(session: Session, user: User, identity: ClerkIdentity) -> None:
    """Copy changed claims onto the user. Missing claims never erase stored values."""
    email, name = _email(identity), _name(identity)
    changed = False
    if email is not None and email != user.email:
        user.email = email
        changed = True
    if name is not None and name != user.full_name:
        user.full_name = name
        changed = True
    if changed:
        session.commit()


def provision_user(session: Session, identity: ClerkIdentity) -> User:
    """The local user for a Clerk identity, created with a personal account on first sight."""
    user = _by_clerk_id(session, identity.clerk_user_id)
    if user is None:
        user = _create(session, identity)
        if user is not None:
            return user
        user = _by_clerk_id(session, identity.clerk_user_id)
        if user is None:  # The concurrent winner rolled back too; one more attempt.
            user = _create(session, identity) or _by_clerk_id(session, identity.clerk_user_id)
        if user is None:
            raise RuntimeError(f"No se pudo aprovisionar el usuario {identity.clerk_user_id!r}.")
    _sync(session, user, identity)
    return user
