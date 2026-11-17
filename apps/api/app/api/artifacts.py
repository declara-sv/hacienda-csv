from __future__ import annotations

import uuid
from urllib.parse import quote

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.deps import CurrentAccount, DbSession, StorageDep
from app.api.errors import not_found
from app.models import Client, OutputArtifact
from app.storage import StoredFileReference
from app.usage import recorder as usage
from app.usage.recorder import UsageScope

router = APIRouter(prefix="/api/artifacts", tags=["artifacts"])


def content_disposition(file_name: str) -> str:
    ascii_name = file_name.encode("ascii", "replace").decode("ascii").replace('"', "_").replace("?", "_")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(file_name)}"


@router.get("/{artifact_id}/download")
def download_artifact(
    artifact_id: uuid.UUID, session: DbSession, storage: StorageDep, account: CurrentAccount
) -> StreamingResponse:
    row = session.execute(
        select(OutputArtifact, Client)
        .join(Client, Client.id == OutputArtifact.client_id)
        .where(OutputArtifact.id == artifact_id, Client.account_id == account.account_id)
    ).first()
    if row is None:
        raise not_found()
    artifact, client = row

    chunks = storage.iter_chunks(
        StoredFileReference(artifact.storage_provider, artifact.storage_container, artifact.storage_path)
    )
    if chunks is None:
        raise not_found()

    usage.artifact_downloaded(
        session,
        UsageScope.for_client(
            client,
            account.user_id,
            filing_period_id=artifact.filing_period_id,
            run_id=artifact.generation_run_id,
            artifact_id=artifact.id,
        ),
        size_bytes=artifact.size_bytes,
        file_name=artifact.file_name,
    )
    session.commit()

    return StreamingResponse(
        chunks,
        media_type=artifact.content_type,
        headers={"Content-Disposition": content_disposition(artifact.file_name)},
    )
