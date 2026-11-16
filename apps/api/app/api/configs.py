from __future__ import annotations

import datetime as dt
import json
import uuid

from fastapi import APIRouter, Response, status
from sqlalchemy import select, update

from app.api.clients import config_dto
from app.api.deps import DbSession
from app.api.errors import not_found, validation_error
from app.api.schemas import ClientConfigDto, ClientConfigRequest
from app.models import ClientConfig
from app.security import CurrentUserId
from app.services.ownership import owned_client

router = APIRouter(prefix="/api/clients/{client_id}/configs", tags=["client-configs"])


def _is_valid_json(value: str | None) -> bool:
    if value is None or not value.strip():
        return True
    try:
        json.loads(value)
    except ValueError:
        return False
    return True


def _check_json(request: ClientConfigRequest) -> None:
    if not _is_valid_json(request.prefill_values_json) or not _is_valid_json(
        request.transformation_rules_json
    ):
        raise validation_error("json", "PrefillValuesJson y TransformationRulesJson deben ser JSON válido.")


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


@router.get("")
def list_configs(client_id: uuid.UUID, session: DbSession, user_id: CurrentUserId) -> list[ClientConfigDto]:
    owned_client(session, client_id, user_id)
    configs = session.scalars(
        select(ClientConfig)
        .where(ClientConfig.client_id == client_id)
        .order_by(ClientConfig.is_active.desc(), ClientConfig.updated_at_utc.desc())
    )
    return [config_dto(c) for c in configs]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_config(
    client_id: uuid.UUID,
    request: ClientConfigRequest,
    session: DbSession,
    user_id: CurrentUserId,
    response: Response,
) -> ClientConfigDto:
    owned_client(session, client_id, user_id)
    _check_json(request)

    if request.is_active:
        session.execute(
            update(ClientConfig)
            .where(ClientConfig.client_id == client_id, ClientConfig.is_active.is_(True))
            .values(is_active=False, updated_at_utc=_now())
        )
    config = ClientConfig(
        client_id=client_id,
        name=request.name,
        prefill_values_json=request.prefill_values_json,
        transformation_rules_json=request.transformation_rules_json,
        is_active=request.is_active,
        updated_at_utc=_now(),
    )
    session.add(config)
    session.commit()
    response.headers["Location"] = f"/api/clients/{client_id}/configs/{config.id}"
    return config_dto(config)


@router.put("/{config_id}")
def update_config(
    client_id: uuid.UUID,
    config_id: uuid.UUID,
    request: ClientConfigRequest,
    session: DbSession,
    user_id: CurrentUserId,
) -> ClientConfigDto:
    owned_client(session, client_id, user_id)
    _check_json(request)
    config = session.scalar(
        select(ClientConfig).where(ClientConfig.id == config_id, ClientConfig.client_id == client_id)
    )
    if config is None:
        raise not_found()

    if request.is_active:
        session.execute(
            update(ClientConfig)
            .where(
                ClientConfig.client_id == client_id,
                ClientConfig.is_active.is_(True),
                ClientConfig.id != config_id,
            )
            .values(is_active=False, updated_at_utc=_now())
        )
    config.name = request.name
    config.prefill_values_json = request.prefill_values_json
    config.transformation_rules_json = request.transformation_rules_json
    config.is_active = request.is_active
    config.updated_at_utc = _now()
    session.commit()
    return config_dto(config)


@router.delete("/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_config(
    client_id: uuid.UUID, config_id: uuid.UUID, session: DbSession, user_id: CurrentUserId
) -> Response:
    owned_client(session, client_id, user_id)
    config = session.scalar(
        select(ClientConfig).where(ClientConfig.id == config_id, ClientConfig.client_id == client_id)
    )
    if config is None:
        raise not_found()
    session.delete(config)
    session.flush()

    has_active = session.scalar(
        select(ClientConfig.id).where(ClientConfig.client_id == client_id, ClientConfig.is_active.is_(True))
    )
    if has_active is None:
        fallback = session.scalar(
            select(ClientConfig)
            .where(ClientConfig.client_id == client_id)
            .order_by(ClientConfig.updated_at_utc.desc())
            .limit(1)
        )
        if fallback is not None:
            fallback.is_active = True
            fallback.updated_at_utc = _now()
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
