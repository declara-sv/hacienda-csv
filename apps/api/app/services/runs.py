"""Generation runs: versioned requests to build the anexo CSVs of a period."""

from __future__ import annotations

import uuid

from sqlalchemy import exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.api.errors import VALIDATION_TITLE, ApiError, conflict, not_found
from app.api.schemas import GenerationRunDto, GenerationRunFileDto, IssueDto, OutputArtifactDto
from app.models import (
    DocumentStatus,
    ExtractionStatus,
    GenerationRun,
    GenerationRunFile,
    RunStatus,
    Upload,
)
from app.services.documents import recompute_period
from app.services.ownership import owned_period
from app.services.uploads import ACTIVE_RUN_STATUSES

ACTIVE_RUN_CONFLICT = "Ya existe una generación en curso para este período."
EXTRACTION_IN_PROGRESS_CONFLICT = (
    "Hay archivos que aún se están leyendo. Espere a que termine la lectura para generar."
)


def to_dto(run: GenerationRun) -> GenerationRunDto:
    return GenerationRunDto(
        id=run.id,
        filing_period_id=run.filing_period_id,
        version=run.version,
        status=run.status,
        error_message=run.error_message,
        created_at_utc=run.created_at_utc,
        started_at_utc=run.started_at_utc,
        completed_at_utc=run.completed_at_utc,
        files=[
            GenerationRunFileDto(
                upload_id=f.upload_id,
                original_file_name=f.original_file_name,
                source_file_kind=f.source_file_kind,
                status=f.status,
                error_message=f.error_message,
            )
            for f in sorted(run.files, key=lambda f: f.original_file_name)
        ],
        artifacts=[
            OutputArtifactDto(
                id=a.id,
                artifact_kind=a.artifact_kind,
                file_name=a.file_name,
                created_at_utc=a.created_at_utc,
                size_bytes=a.size_bytes,
                row_count=a.row_count,
            )
            for a in sorted(run.artifacts, key=lambda a: (a.file_name, a.created_at_utc))
        ],
        issues=[IssueDto.model_validate(i) for i in run.issues or []],
    )


def create_run(
    session: Session, client_id: uuid.UUID, period_id: uuid.UUID, user_id: uuid.UUID
) -> GenerationRunDto:
    client, period = owned_period(session, client_id, period_id, user_id)

    uploads = list(
        session.scalars(
            select(Upload)
            .where(Upload.filing_period_id == period_id, Upload.client_id == client_id)
            .order_by(Upload.created_at_utc)
        )
    )
    if not uploads:
        raise ApiError(400, VALIDATION_TITLE, {"uploads": ["El período no tiene archivos para generar."]})

    if any(
        u.extraction_status in (ExtractionStatus.PENDING.value, ExtractionStatus.RUNNING.value)
        for u in uploads
    ):
        raise conflict(EXTRACTION_IN_PROGRESS_CONFLICT)

    active = session.scalar(
        select(
            exists().where(
                GenerationRun.filing_period_id == period_id, GenerationRun.status.in_(ACTIVE_RUN_STATUSES)
            )
        )
    )
    if active:
        raise conflict(ACTIVE_RUN_CONFLICT)

    docs = recompute_period(session, period, client)
    session.commit()

    included = [d for d in docs if not d.excluded]
    if not included:
        raise ApiError(
            400, VALIDATION_TITLE, {"documents": ["El período no tiene documentos incluidos para generar."]}
        )
    with_errors = sum(1 for d in included if d.status == DocumentStatus.ERROR.value)
    if with_errors:
        noun = "documento tiene" if with_errors == 1 else "documentos tienen"
        raise ApiError(
            400,
            VALIDATION_TITLE,
            {"documents": [f"{with_errors} {noun} errores. Corríjalos o exclúyalos antes de generar."]},
        )

    max_version = session.scalar(
        select(func.max(GenerationRun.version)).where(GenerationRun.filing_period_id == period_id)
    )
    run = GenerationRun(
        client_id=client_id,
        filing_period_id=period_id,
        requested_by_user_id=user_id,
        version=(max_version or 0) + 1,
        status=RunStatus.PENDING.value,
        issues=[],
    )
    contributing = {d.upload_id for d in included}
    for upload in uploads:
        if upload.id in contributing:
            run.files.append(
                GenerationRunFile(
                    upload_id=upload.id,
                    original_file_name=upload.original_file_name,
                    source_file_kind=upload.source_file_kind,
                )
            )
    session.add(run)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise conflict(ACTIVE_RUN_CONFLICT) from exc
    return to_dto(run)


def _runs_query():
    return select(GenerationRun).options(
        selectinload(GenerationRun.files), selectinload(GenerationRun.artifacts)
    )


def list_runs(
    session: Session, client_id: uuid.UUID, period_id: uuid.UUID, user_id: uuid.UUID
) -> list[GenerationRunDto]:
    owned_period(session, client_id, period_id, user_id)
    runs = session.scalars(
        _runs_query()
        .where(GenerationRun.filing_period_id == period_id)
        .order_by(GenerationRun.version.desc())
    )
    return [to_dto(r) for r in runs]


def get_run(
    session: Session, client_id: uuid.UUID, period_id: uuid.UUID, run_id: uuid.UUID, user_id: uuid.UUID
) -> GenerationRunDto:
    owned_period(session, client_id, period_id, user_id)
    run = session.scalar(
        _runs_query().where(GenerationRun.id == run_id, GenerationRun.filing_period_id == period_id)
    )
    if run is None:
        raise not_found()
    return to_dto(run)
