from __future__ import annotations

import uuid

from fastapi import APIRouter, Response, status
from sqlalchemy import func, select

from app.api.deps import CurrentAccount, DbSession
from app.api.errors import not_found, validation_error
from app.api.schemas import FilingPeriodDto, FilingPeriodRequest
from app.models import FilingPeriod, Upload
from app.services.documents import recompute_period
from app.services.ownership import owned_client

router = APIRouter(prefix="/api/clients/{client_id}/periods", tags=["filing-periods"])


def _uploads_count(period_id_column):
    return select(func.count(Upload.id)).where(Upload.filing_period_id == period_id_column).scalar_subquery()


def _dto(period: FilingPeriod, uploads_count: int) -> FilingPeriodDto:
    return FilingPeriodDto(
        id=period.id,
        year=period.year,
        month=period.month,
        created_at_utc=period.created_at_utc,
        uploads_count=uploads_count,
    )


@router.get("")
def list_periods(client_id: uuid.UUID, session: DbSession, account: CurrentAccount) -> list[FilingPeriodDto]:
    owned_client(session, client_id, account.account_id)
    rows = session.execute(
        select(FilingPeriod, _uploads_count(FilingPeriod.id))
        .where(FilingPeriod.client_id == client_id)
        .order_by(FilingPeriod.year.desc(), FilingPeriod.month.desc())
    )
    return [_dto(p, count) for p, count in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_period(
    client_id: uuid.UUID,
    request: FilingPeriodRequest,
    session: DbSession,
    account: CurrentAccount,
    response: Response,
) -> FilingPeriodDto:
    owned_client(session, client_id, account.account_id)
    exists = session.scalar(
        select(FilingPeriod.id).where(
            FilingPeriod.client_id == client_id,
            FilingPeriod.year == request.year,
            FilingPeriod.month == request.month,
        )
    )
    if exists is not None:
        raise validation_error("period", "El período ya existe para este cliente.")

    period = FilingPeriod(client_id=client_id, year=request.year, month=request.month)
    session.add(period)
    session.commit()
    response.headers["Location"] = f"/api/clients/{client_id}/periods/{period.id}"
    return _dto(period, 0)


@router.put("/{period_id}")
def update_period(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    request: FilingPeriodRequest,
    session: DbSession,
    account: CurrentAccount,
) -> FilingPeriodDto:
    client = owned_client(session, client_id, account.account_id)
    period = session.scalar(
        select(FilingPeriod).where(FilingPeriod.id == period_id, FilingPeriod.client_id == client_id)
    )
    if period is None:
        raise not_found()

    duplicate = session.scalar(
        select(FilingPeriod.id).where(
            FilingPeriod.client_id == client_id,
            FilingPeriod.id != period_id,
            FilingPeriod.year == request.year,
            FilingPeriod.month == request.month,
        )
    )
    if duplicate is not None:
        raise validation_error("period", "Ya existe otro período con ese año y mes.")

    period.year = request.year
    period.month = request.month
    session.flush()
    # "Fecha fuera del período" depends on year/month.
    recompute_period(session, period, client)
    session.commit()
    count = session.scalar(select(func.count(Upload.id)).where(Upload.filing_period_id == period_id)) or 0
    return _dto(period, count)


@router.delete("/{period_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_period(
    client_id: uuid.UUID, period_id: uuid.UUID, session: DbSession, account: CurrentAccount
) -> Response:
    owned_client(session, client_id, account.account_id)
    period = session.scalar(
        select(FilingPeriod).where(FilingPeriod.id == period_id, FilingPeriod.client_id == client_id)
    )
    if period is None:
        raise not_found()
    session.delete(period)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
