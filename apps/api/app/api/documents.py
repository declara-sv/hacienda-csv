from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.deps import DbSession
from app.api.schemas import DocumentBulkRequest, DocumentDto, DocumentPatchRequest
from app.security import CurrentUserId
from app.services import documents as service

router = APIRouter(prefix="/api/clients/{client_id}/periods/{period_id}/documents", tags=["documents"])


@router.get("")
def list_documents(
    client_id: uuid.UUID, period_id: uuid.UUID, session: DbSession, user_id: CurrentUserId
) -> list[DocumentDto]:
    return service.list_documents(session, client_id, period_id, user_id)


@router.post("/bulk")
def bulk_update(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    request: DocumentBulkRequest,
    session: DbSession,
    user_id: CurrentUserId,
) -> list[DocumentDto]:
    """Applies the changes to the given documents and returns the whole period list."""
    return service.bulk_update(session, client_id, period_id, user_id, request)


@router.patch("/{document_id}")
def update_document(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    document_id: uuid.UUID,
    request: DocumentPatchRequest,
    session: DbSession,
    user_id: CurrentUserId,
) -> DocumentDto:
    return service.update_document(session, client_id, period_id, document_id, user_id, request)
