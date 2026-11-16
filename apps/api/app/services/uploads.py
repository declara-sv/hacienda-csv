"""Uploads of a filing period: store the file, track extraction, delete, re-extract."""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from pathlib import PurePath

from sqlalchemy import delete, exists, func, select, update
from sqlalchemy.orm import Session

from app.api.errors import ApiError, conflict, not_found, validation_error
from app.api.schemas import UploadDto
from app.config import Settings
from app.models import (
    DteDocument,
    ExtractionStatus,
    GenerationRun,
    GenerationRunFile,
    RunStatus,
    Upload,
)
from app.services.documents import recompute_period
from app.services.ownership import owned_period
from app.storage import FileStorage, StoredFileReference

logger = logging.getLogger(__name__)

SOURCE_FILE_KINDS = ("Excel", "PDF")
ACTIVE_RUN_STATUSES = (RunStatus.PENDING.value, RunStatus.RUNNING.value)
_INVALID_FILE_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

ACTIVE_RUN_CONFLICT = "El archivo está siendo usado por una generación en curso."
EXTRACTION_RUNNING_CONFLICT = "El archivo se está leyendo en este momento. Intente de nuevo en unos segundos."


def is_valid_file_type(file_name: str, source_file_kind: str) -> bool:
    extension = PurePath(file_name).suffix.lower()
    if source_file_kind == "Excel":
        return extension in (".xls", ".xlsx")
    if source_file_kind == "PDF":
        return extension == ".pdf"
    return False


def sanitize_file_name(name: str) -> str:
    cleaned = _INVALID_FILE_CHARS.sub("_", name).strip()
    return cleaned or "archivo"


def included_in_latest_run(session: Session, period_id: uuid.UUID) -> set[uuid.UUID]:
    latest = session.scalar(
        select(GenerationRun.id)
        .where(GenerationRun.filing_period_id == period_id, GenerationRun.status == RunStatus.COMPLETED.value)
        .order_by(GenerationRun.version.desc())
        .limit(1)
    )
    if latest is None:
        return set()
    return set(
        session.scalars(
            select(GenerationRunFile.upload_id).where(
                GenerationRunFile.generation_run_id == latest, GenerationRunFile.upload_id.is_not(None)
            )
        )
    )


def documents_count(session: Session, upload_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not upload_ids:
        return {}
    rows = session.execute(
        select(DteDocument.upload_id, func.count())
        .where(DteDocument.upload_id.in_(upload_ids))
        .group_by(DteDocument.upload_id)
    )
    return {upload_id: count for upload_id, count in rows}


def to_dto(upload: Upload, *, included: bool, count: int) -> UploadDto:
    return UploadDto(
        id=upload.id,
        filing_period_id=upload.filing_period_id,
        original_file_name=upload.original_file_name,
        source_file_kind=upload.source_file_kind,
        content_type=upload.content_type,
        size_bytes=upload.size_bytes,
        created_at_utc=upload.created_at_utc,
        included_in_latest_run=included,
        extraction_status=upload.extraction_status,
        extraction_error=upload.extraction_error,
        documents_count=count,
    )


def _single_dto(session: Session, upload: Upload) -> UploadDto:
    included = included_in_latest_run(session, upload.filing_period_id)
    count = documents_count(session, [upload.id]).get(upload.id, 0)
    return to_dto(upload, included=upload.id in included, count=count)


def list_uploads(
    session: Session, client_id: uuid.UUID, period_id: uuid.UUID, user_id: uuid.UUID
) -> list[UploadDto]:
    owned_period(session, client_id, period_id, user_id)
    uploads = list(
        session.scalars(
            select(Upload)
            .where(Upload.client_id == client_id, Upload.filing_period_id == period_id)
            .order_by(Upload.created_at_utc.desc(), Upload.id.desc())
        )
    )
    included = included_in_latest_run(session, period_id)
    counts = documents_count(session, [u.id for u in uploads])
    return [to_dto(u, included=u.id in included, count=counts.get(u.id, 0)) for u in uploads]


def create_upload(
    session: Session,
    storage: FileStorage,
    settings: Settings,
    *,
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    user_id: uuid.UUID,
    file_name: str,
    content_type: str | None,
    content: bytes,
    source_file_kind: str,
) -> UploadDto:
    _, period = owned_period(session, client_id, period_id, user_id)

    if source_file_kind not in SOURCE_FILE_KINDS:
        raise validation_error("sourceFileKind", "El tipo debe ser Excel o PDF.")
    if len(content) > settings.max_upload_bytes:
        limit_mb = settings.max_upload_bytes // 1_000_000
        raise ApiError(413, f"El archivo excede el tamaño máximo de {limit_mb} MB.")
    if not content:
        raise validation_error("file", "El archivo está vacío.")
    if not is_valid_file_type(file_name, source_file_kind):
        raise validation_error("file", "El tipo de archivo no corresponde al tipo seleccionado (Excel/PDF).")

    pure = PurePath(file_name)
    extension = pure.suffix.lower()
    safe = sanitize_file_name(pure.stem)
    path = f"{client_id}/{period.year:04d}/{period.month:02d}/{uuid.uuid4()}_{safe}{extension}"
    content_type = content_type or "application/octet-stream"
    stored = storage.save(settings.storage_upload_container, path, content, content_type)

    upload = Upload(
        client_id=client_id,
        filing_period_id=period_id,
        uploaded_by_user_id=user_id,
        original_file_name=file_name[:260],
        content_type=content_type[:120],
        source_file_kind=source_file_kind,
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        storage_provider=stored.provider,
        storage_container=stored.container,
        storage_path=stored.path,
        extraction_status=ExtractionStatus.PENDING.value,
    )
    session.add(upload)
    session.commit()
    return to_dto(upload, included=False, count=0)


def _owned_upload(
    session: Session, client_id: uuid.UUID, period_id: uuid.UUID, upload_id: uuid.UUID, user_id: uuid.UUID
):
    client, period = owned_period(session, client_id, period_id, user_id)
    upload = session.scalar(
        select(Upload).where(
            Upload.id == upload_id, Upload.filing_period_id == period_id, Upload.client_id == client_id
        )
    )
    if upload is None:
        raise not_found()
    return client, period, upload


def _referenced_by_active_run(session: Session, upload_id: uuid.UUID) -> bool:
    return bool(
        session.scalar(
            select(
                exists().where(
                    GenerationRunFile.upload_id == upload_id,
                    GenerationRunFile.generation_run_id == GenerationRun.id,
                    GenerationRun.status.in_(ACTIVE_RUN_STATUSES),
                )
            )
        )
    )


def delete_upload(
    session: Session,
    storage: FileStorage,
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    upload_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    client, period, upload = _owned_upload(session, client_id, period_id, upload_id, user_id)
    if _referenced_by_active_run(session, upload_id):
        raise conflict(ACTIVE_RUN_CONFLICT)

    reference = StoredFileReference(upload.storage_provider, upload.storage_container, upload.storage_path)
    session.delete(upload)
    session.flush()
    recompute_period(session, period, client)
    session.commit()

    try:
        storage.delete(reference)
    except Exception:
        logger.warning(
            "No se pudo eliminar el archivo de almacenamiento para el upload %s.", upload_id, exc_info=True
        )


def reextract_upload(
    session: Session,
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    upload_id: uuid.UUID,
    user_id: uuid.UUID,
) -> UploadDto:
    client, period, upload = _owned_upload(session, client_id, period_id, upload_id, user_id)
    if _referenced_by_active_run(session, upload_id):
        raise conflict(ACTIVE_RUN_CONFLICT)

    reset = session.execute(
        update(Upload)
        .where(Upload.id == upload_id, Upload.extraction_status != ExtractionStatus.RUNNING.value)
        .values(
            extraction_status=ExtractionStatus.PENDING.value,
            extraction_error=None,
            extraction_started_at_utc=None,
            extraction_completed_at_utc=None,
        )
    )
    if reset.rowcount == 0:
        session.rollback()
        raise conflict(EXTRACTION_RUNNING_CONFLICT)

    session.execute(delete(DteDocument).where(DteDocument.upload_id == upload_id))
    session.flush()
    session.expire_all()
    client, period, upload = _owned_upload(session, client_id, period_id, upload_id, user_id)
    recompute_period(session, period, client)
    session.commit()
    return _single_dto(session, upload)
