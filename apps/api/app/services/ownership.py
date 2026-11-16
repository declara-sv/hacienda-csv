"""Account scoping: resources of other accounts behave as missing (404)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.errors import not_found
from app.models import Client, FilingPeriod


def owned_client(session: Session, client_id: uuid.UUID, account_id: uuid.UUID) -> Client:
    client = session.scalar(select(Client).where(Client.id == client_id, Client.account_id == account_id))
    if client is None:
        raise not_found()
    return client


def owned_period(
    session: Session, client_id: uuid.UUID, period_id: uuid.UUID, account_id: uuid.UUID
) -> tuple[Client, FilingPeriod]:
    row = session.execute(
        select(Client, FilingPeriod)
        .join(FilingPeriod, FilingPeriod.client_id == Client.id)
        .where(Client.id == client_id, Client.account_id == account_id, FilingPeriod.id == period_id)
    ).first()
    if row is None:
        raise not_found()
    return row[0], row[1]
