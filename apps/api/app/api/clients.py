from __future__ import annotations

import uuid

from fastapi import APIRouter, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import DbSession
from app.api.errors import not_found
from app.api.schemas import (
    ClientConfigDto,
    ClientDetailDto,
    ClientRequest,
    ClientSummaryDto,
    FilingPeriodSummaryDto,
)
from app.models import Client, ClientConfig, FilingPeriod
from app.security import CurrentUserId
from app.services.documents import check_renta_code, recompute_client
from app.services.ownership import owned_client

router = APIRouter(prefix="/api/clients", tags=["clients"])


def config_dto(config: ClientConfig) -> ClientConfigDto:
    return ClientConfigDto.model_validate(config)


def sorted_configs(configs: list[ClientConfig]) -> list[ClientConfig]:
    return sorted(configs, key=lambda c: (c.is_active, c.updated_at_utc), reverse=True)


def detail_dto(client: Client) -> ClientDetailDto:
    return ClientDetailDto(
        id=client.id,
        name=client.name,
        tax_id=client.tax_id,
        notes=client.notes,
        nit=client.nit,
        nrc=client.nrc,
        default_tipo_operacion=client.default_tipo_operacion,
        default_tipo_ingreso=client.default_tipo_ingreso,
        created_at_utc=client.created_at_utc,
        configurations=[config_dto(c) for c in sorted_configs(client.configurations)],
        filing_periods=[
            FilingPeriodSummaryDto.model_validate(p)
            for p in sorted(client.filing_periods, key=lambda p: (p.year, p.month), reverse=True)
        ],
    )


def _load_detail(session: Session, client_id: uuid.UUID, user_id: uuid.UUID) -> Client:
    client = session.scalar(
        select(Client)
        .options(selectinload(Client.configurations), selectinload(Client.filing_periods))
        .where(Client.id == client_id, Client.owner_user_id == user_id)
        .execution_options(populate_existing=True)
    )
    if client is None:
        raise not_found()
    return client


def _validate_codes(request: ClientRequest) -> None:
    check_renta_code("tipo_operacion", request.default_tipo_operacion, "defaultTipoOperacion")
    check_renta_code("tipo_ingreso", request.default_tipo_ingreso, "defaultTipoIngreso")


@router.get("")
def list_clients(session: DbSession, user_id: CurrentUserId) -> list[ClientSummaryDto]:
    periods_count = (
        select(func.count(FilingPeriod.id)).where(FilingPeriod.client_id == Client.id).scalar_subquery()
    )
    rows = session.execute(
        select(Client, periods_count).where(Client.owner_user_id == user_id).order_by(Client.name)
    )
    return [
        ClientSummaryDto(
            id=c.id,
            name=c.name,
            tax_id=c.tax_id,
            nit=c.nit,
            nrc=c.nrc,
            default_tipo_operacion=c.default_tipo_operacion,
            default_tipo_ingreso=c.default_tipo_ingreso,
            filing_periods_count=count,
            created_at_utc=c.created_at_utc,
        )
        for c, count in rows
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_client(
    request: ClientRequest, session: DbSession, user_id: CurrentUserId, response: Response
) -> ClientDetailDto:
    _validate_codes(request)
    client = Client(
        owner_user_id=user_id,
        name=request.name,
        tax_id=request.tax_id,
        notes=request.notes,
        nit=request.nit,
        nrc=request.nrc,
        default_tipo_operacion=request.default_tipo_operacion,
        default_tipo_ingreso=request.default_tipo_ingreso,
    )
    client.configurations.append(ClientConfig(name="Base", prefill_values_json="{}", is_active=True))
    session.add(client)
    session.commit()
    response.headers["Location"] = f"/api/clients/{client.id}"
    return detail_dto(_load_detail(session, client.id, user_id))


@router.get("/{client_id}")
def get_client(client_id: uuid.UUID, session: DbSession, user_id: CurrentUserId) -> ClientDetailDto:
    return detail_dto(_load_detail(session, client_id, user_id))


@router.put("/{client_id}")
def update_client(
    client_id: uuid.UUID, request: ClientRequest, session: DbSession, user_id: CurrentUserId
) -> ClientDetailDto:
    client = owned_client(session, client_id, user_id)
    _validate_codes(request)

    client.name = request.name
    client.tax_id = request.tax_id
    client.notes = request.notes
    # Structured fields are only replaced when sent, so older clients that omit them keep the values.
    for field in ("nit", "nrc", "default_tipo_operacion", "default_tipo_ingreso"):
        if field in request.model_fields_set:
            setattr(client, field, getattr(request, field))
    session.flush()
    recompute_client(session, client)
    session.commit()
    return detail_dto(_load_detail(session, client_id, user_id))


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_client(client_id: uuid.UUID, session: DbSession, user_id: CurrentUserId) -> Response:
    client = owned_client(session, client_id, user_id)
    session.delete(client)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
