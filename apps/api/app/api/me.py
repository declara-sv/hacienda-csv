from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import CurrentAccount, CurrentUser, DbSession
from app.api.schemas import MeAccountDto, MeDto, MeUserDto
from app.models import Account, AccountMember

router = APIRouter(prefix="/api", tags=["me"])


@router.get("/me")
def me(session: DbSession, user: CurrentUser, account: CurrentAccount) -> MeDto:
    """The signed-in user and the account the request acts on (`X-Account-Id` or the default)."""
    current, role = session.execute(
        select(Account, AccountMember.role)
        .join(AccountMember, AccountMember.account_id == Account.id)
        .where(Account.id == account.account_id, AccountMember.user_id == user.id)
    ).one()
    return MeDto(
        user=MeUserDto(id=user.id, email=user.email, full_name=user.full_name),
        account=MeAccountDto(id=current.id, name=current.name, role=role),
    )
