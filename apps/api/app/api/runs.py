from __future__ import annotations

import uuid

from fastapi import APIRouter, Response, status

from app.api.deps import DbSession
from app.api.schemas import GenerationRunDto
from app.security import CurrentUserId
from app.services import runs as service

router = APIRouter(prefix="/api/clients/{client_id}/periods/{period_id}/runs", tags=["generation-runs"])


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def create_run(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    session: DbSession,
    user_id: CurrentUserId,
    response: Response,
) -> GenerationRunDto:
    run = service.create_run(session, client_id, period_id, user_id)
    response.headers["Location"] = f"/api/clients/{client_id}/periods/{period_id}/runs/{run.id}"
    return run


@router.get("")
def list_runs(
    client_id: uuid.UUID, period_id: uuid.UUID, session: DbSession, user_id: CurrentUserId
) -> list[GenerationRunDto]:
    return service.list_runs(session, client_id, period_id, user_id)


@router.get("/{run_id}")
def get_run(
    client_id: uuid.UUID, period_id: uuid.UUID, run_id: uuid.UUID, session: DbSession, user_id: CurrentUserId
) -> GenerationRunDto:
    return service.get_run(session, client_id, period_id, run_id, user_id)
