from __future__ import annotations

import uuid
from urllib.parse import quote

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.deps import DbSession, StorageDep
from app.api.errors import not_found
from app.models import Client, OutputArtifact
from app.security import CurrentUserId
from app.storage import StoredFileReference

router = APIRouter(prefix="/api/artifacts", tags=["artifacts"])


def content_disposition(file_name: str) -> str:
    ascii_name = file_name.encode("ascii", "replace").decode("ascii").replace('"', "_").replace("?", "_")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(file_name)}"


@router.get("/{artifact_id}/download")
def download_artifact(
    artifact_id: uuid.UUID, session: DbSession, storage: StorageDep, user_id: CurrentUserId
) -> StreamingResponse:
    artifact = session.scalar(
        select(OutputArtifact)
        .join(Client, Client.id == OutputArtifact.client_id)
        .where(OutputArtifact.id == artifact_id, Client.owner_user_id == user_id)
    )
    if artifact is None:
        raise not_found()

    chunks = storage.iter_chunks(
        StoredFileReference(artifact.storage_provider, artifact.storage_container, artifact.storage_path)
    )
    if chunks is None:
        raise not_found()

    return StreamingResponse(
        chunks,
        media_type=artifact.content_type,
        headers={"Content-Disposition": content_disposition(artifact.file_name)},
    )
