from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, Response, UploadFile, status

from app.api.deps import CurrentAccount, DbSession, SettingsDep, StorageDep
from app.api.errors import ApiError
from app.api.schemas import UploadDto
from app.services import uploads as service

router = APIRouter(prefix="/api/clients/{client_id}/periods/{period_id}/uploads", tags=["uploads"])


@router.get("")
def list_uploads(
    client_id: uuid.UUID, period_id: uuid.UUID, session: DbSession, account: CurrentAccount
) -> list[UploadDto]:
    return service.list_uploads(session, client_id, period_id, account)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_upload(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    file: Annotated[UploadFile, File()],
    source_file_kind: Annotated[str, Form(alias="sourceFileKind")],
    session: DbSession,
    storage: StorageDep,
    settings: SettingsDep,
    account: CurrentAccount,
    response: Response,
) -> UploadDto:
    # Read at most limit+1 bytes so an oversized upload is rejected without loading all of it.
    content = file.file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        limit_mb = settings.max_upload_bytes // 1_000_000
        raise ApiError(413, f"El archivo excede el tamaño máximo de {limit_mb} MB.")

    upload = service.create_upload(
        session,
        storage,
        settings,
        client_id=client_id,
        period_id=period_id,
        account=account,
        file_name=file.filename or "archivo",
        content_type=file.content_type,
        content=content,
        source_file_kind=source_file_kind.strip(),
    )
    response.headers["Location"] = f"/api/clients/{client_id}/periods/{period_id}/uploads/{upload.id}"
    return upload


@router.delete("/{upload_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_upload(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    upload_id: uuid.UUID,
    session: DbSession,
    storage: StorageDep,
    account: CurrentAccount,
) -> Response:
    service.delete_upload(session, storage, client_id, period_id, upload_id, account)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{upload_id}/reextract")
def reextract_upload(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    upload_id: uuid.UUID,
    session: DbSession,
    account: CurrentAccount,
) -> UploadDto:
    return service.reextract_upload(session, client_id, period_id, upload_id, account)
