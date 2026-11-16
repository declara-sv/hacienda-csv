"""In-process background worker: reads uploaded PDFs and processes generation runs.

Work is claimed with `UPDATE ... WHERE id = (SELECT ... FOR UPDATE SKIP LOCKED) RETURNING`, so several
API instances can poll the same database. The processor functions are public so tests can drive
them synchronously without the thread.
"""

from __future__ import annotations

import datetime as dt
import logging
import threading
import uuid
from collections.abc import Callable

from sqlalchemy import delete, select, text, update
from sqlalchemy.orm import Session, selectinload, sessionmaker

from app.config import Settings
from app.domain import ExtractionResult, IssueSeverity
from app.models import (
    Client,
    DteDocument,
    ExtractionStatus,
    FilingPeriod,
    GenerationRun,
    OutputArtifact,
    RunFileStatus,
    RunStatus,
    Upload,
)
from app.services import integrations
from app.services.documents import apply_record, client_profile, recompute_period, reviewed_document
from app.storage import FileStorage, StoredFileReference

logger = logging.getLogger(__name__)

Extractor = Callable[[bytes], ExtractionResult]

CSV_CONTENT_TYPE = "text/csv; charset=windows-1252"
EXCEL_NOT_SUPPORTED = "La lectura de archivos Excel aún no está disponible."
MAX_MESSAGE = 2000
NO_SALES_DOCUMENTS = "ningún documento incluido se reporta en los anexos de ventas."

_CLAIM_RUN_SQL = text(
    """
    UPDATE generation_runs
    SET status = 'Running', started_at_utc = now()
    WHERE id = (
        SELECT id FROM generation_runs
        WHERE status = 'Pending'
        ORDER BY created_at_utc
        LIMIT 1
        FOR UPDATE SKIP LOCKED
    )
    RETURNING id
    """
)

_CLAIM_EXTRACTION_SQL = text(
    """
    UPDATE uploads
    SET extraction_status = 'Running', extraction_started_at_utc = now(),
        extraction_completed_at_utc = NULL, extraction_error = NULL
    WHERE id = (
        SELECT id FROM uploads
        WHERE extraction_status = 'Pending'
        ORDER BY created_at_utc
        LIMIT 1
        FOR UPDATE SKIP LOCKED
    )
    RETURNING id
    """
)


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _truncate(message: str) -> str:
    return message[:MAX_MESSAGE]


# --- Generation runs ----------------------------------------------------------------------------


def try_claim_run(session: Session) -> uuid.UUID | None:
    """Atomically move the oldest Pending run to Running. None when nothing is pending."""
    run_id = session.execute(_CLAIM_RUN_SQL).scalar_one_or_none()
    session.commit()
    return run_id


def recover_stuck_runs(session: Session, timeout_minutes: int) -> int:
    """Fail runs stuck in Running longer than the timeout. Returns how many were failed."""
    cutoff = _now() - dt.timedelta(minutes=timeout_minutes)
    result = session.execute(
        update(GenerationRun)
        .where(
            GenerationRun.status == RunStatus.RUNNING.value,
            GenerationRun.started_at_utc.is_not(None),
            GenerationRun.started_at_utc < cutoff,
        )
        .values(
            status=RunStatus.FAILED.value,
            completed_at_utc=_now(),
            error_message=f"La generación excedió el tiempo máximo de {timeout_minutes} minutos.",
        )
    )
    session.commit()
    if result.rowcount:
        logger.warning("Se marcaron %s generaciones atascadas como fallidas.", result.rowcount)
    return result.rowcount


def _fail_run(session: Session, run_id: uuid.UUID, message: str) -> None:
    session.rollback()
    run = session.get(GenerationRun, run_id, populate_existing=True)
    if run is None:
        return
    run.status = RunStatus.FAILED.value
    run.completed_at_utc = _now()
    run.error_message = _truncate(message)
    session.commit()


def process_run(session: Session, storage: FileStorage, settings: Settings, run_id: uuid.UUID) -> None:
    run = session.scalar(
        select(GenerationRun)
        .options(selectinload(GenerationRun.files))
        .where(GenerationRun.id == run_id)
        .execution_options(populate_existing=True)
    )
    if run is None:
        logger.warning("Generación %s no encontrada al procesar.", run_id)
        return

    try:
        period = session.get(FilingPeriod, run.filing_period_id)
        client = session.get(Client, run.client_id)
        if period is None or client is None:
            raise RuntimeError("El período o el cliente de la generación ya no existe.")

        docs = [d for d in recompute_period(session, period, client) if not d.excluded]
        if not docs:
            _fail_run(session, run_id, "No hay documentos incluidos para generar.")
            return

        result = integrations.build_sales_anexos(
            year=period.year,
            month=period.month,
            client=client_profile(client),
            documents=[reviewed_document(d, client) for d in docs],
        )
        run.issues = [i.model_dump(mode="json") for i in result.issues]
        errors = [i for i in result.issues if i.severity == IssueSeverity.ERROR]
        if errors or not result.files:
            reason = errors[0].message if errors else NO_SALES_DOCUMENTS
            run.status = RunStatus.FAILED.value
            run.completed_at_utc = _now()
            run.error_message = _truncate(f"No se generaron los anexos: {reason}")
            session.commit()
            return

        for output in result.files:
            path = (
                f"{run.client_id}/{period.year:04d}/{period.month:02d}/run-{run.version}/{output.file_name}"
            )
            stored = storage.save(settings.storage_output_container, path, output.content, CSV_CONTENT_TYPE)
            session.add(
                OutputArtifact(
                    generation_run_id=run.id,
                    client_id=run.client_id,
                    filing_period_id=run.filing_period_id,
                    artifact_kind="CSV",
                    file_name=output.file_name,
                    content_type=CSV_CONTENT_TYPE,
                    size_bytes=len(output.content),
                    row_count=output.row_count,
                    storage_provider=stored.provider,
                    storage_container=stored.container,
                    storage_path=stored.path,
                )
            )

        contributing = {d.upload_id for d in docs}
        for file in run.files:
            if file.upload_id is None:
                file.status = RunFileStatus.FAILED.value
                file.error_message = "El archivo fue eliminado antes de generar."
            elif file.upload_id in contributing:
                file.status = RunFileStatus.INCLUDED.value
                file.error_message = None
            else:
                file.status = RunFileStatus.FAILED.value
                file.error_message = "El archivo ya no tiene documentos incluidos."

        run.status = RunStatus.COMPLETED.value
        run.completed_at_utc = _now()
        run.error_message = None
        session.commit()
    except Exception as exc:
        logger.exception("Falló la generación %s.", run_id)
        _fail_run(session, run_id, str(exc) or exc.__class__.__name__)


# --- Upload extraction --------------------------------------------------------------------------


def try_claim_extraction(session: Session) -> uuid.UUID | None:
    """Atomically move the oldest Pending upload extraction to Running."""
    upload_id = session.execute(_CLAIM_EXTRACTION_SQL).scalar_one_or_none()
    session.commit()
    return upload_id


def recover_stuck_extractions(session: Session, timeout_minutes: int) -> int:
    cutoff = _now() - dt.timedelta(minutes=timeout_minutes)
    result = session.execute(
        update(Upload)
        .where(
            Upload.extraction_status == ExtractionStatus.RUNNING.value,
            Upload.extraction_started_at_utc.is_not(None),
            Upload.extraction_started_at_utc < cutoff,
        )
        .values(
            extraction_status=ExtractionStatus.FAILED.value,
            extraction_completed_at_utc=_now(),
            extraction_error=f"La lectura del archivo excedió el tiempo máximo de {timeout_minutes} minutos.",
        )
    )
    session.commit()
    if result.rowcount:
        logger.warning("Se marcaron %s lecturas atascadas como fallidas.", result.rowcount)
    return result.rowcount


class _ExtractionFailure(Exception):
    pass


def _no_records_message(result: ExtractionResult) -> str:
    errors = [i.message for i in result.issues if i.severity == IssueSeverity.ERROR]
    return errors[0] if errors else "No se encontraron documentos en el archivo."


def process_extraction(
    session: Session,
    storage: FileStorage,
    settings: Settings,
    upload_id: uuid.UUID,
    *,
    extract: Extractor | None = None,
) -> None:
    """Read a claimed upload and replace its documents. Never raises."""
    upload = session.get(Upload, upload_id, populate_existing=True)
    if upload is None or upload.extraction_status != ExtractionStatus.RUNNING.value:
        session.rollback()
        return
    claimed_at = upload.extraction_started_at_utc
    kind = upload.source_file_kind
    reference = StoredFileReference(upload.storage_provider, upload.storage_container, upload.storage_path)
    # End the transaction before the (possibly slow) extraction.
    session.commit()

    result: ExtractionResult | None = None
    error: str | None = None
    try:
        if kind != "PDF":
            raise _ExtractionFailure(EXCEL_NOT_SUPPORTED)
        content = storage.read(reference)
        if content is None:
            raise _ExtractionFailure("No se encontró el archivo en el almacenamiento.")
        extractor = extract or (lambda data: integrations.extract_pdf(data, settings))
        result = extractor(content)
        if not result.records:
            raise _ExtractionFailure(_no_records_message(result))
    except _ExtractionFailure as exc:
        error = str(exc)
    except Exception as exc:
        logger.exception("Falló la lectura del upload %s.", upload_id)
        error = f"Error al leer el archivo: {exc}" if str(exc) else "Error al leer el archivo."

    try:
        _save_extraction(session, upload_id, claimed_at, result, error)
    except Exception:
        logger.exception("No se pudo guardar la lectura del upload %s.", upload_id)
        session.rollback()


def _save_extraction(
    session: Session,
    upload_id: uuid.UUID,
    claimed_at: dt.datetime | None,
    result: ExtractionResult | None,
    error: str | None,
) -> None:
    upload = session.scalar(
        select(Upload)
        .where(Upload.id == upload_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    # Deleted, re-queued or recovered while we were reading: drop this result.
    if (
        upload is None
        or upload.extraction_status != ExtractionStatus.RUNNING.value
        or upload.extraction_started_at_utc != claimed_at
    ):
        session.rollback()
        return

    session.execute(delete(DteDocument).where(DteDocument.upload_id == upload_id))
    upload.extraction_completed_at_utc = _now()

    if error is not None or result is None:
        upload.extraction_status = ExtractionStatus.FAILED.value
        upload.extraction_error = _truncate(error or "Error al leer el archivo.")
        session.commit()
        return

    # Result-level issues can only be attributed to a document when there is exactly one.
    extraction_issues = [i.model_dump(mode="json") for i in result.issues] if len(result.records) == 1 else []
    for record in result.records:
        doc = DteDocument(
            upload_id=upload.id,
            client_id=upload.client_id,
            filing_period_id=upload.filing_period_id,
            extraction_method=result.method.value,
            extracted=record.model_dump(mode="json"),
            extraction_issues=extraction_issues,
            issues=[],
            edited=False,
            excluded=False,
        )
        apply_record(doc, record)
        session.add(doc)

    upload.extraction_status = ExtractionStatus.COMPLETED.value
    upload.extraction_error = None
    session.flush()

    period = session.get(FilingPeriod, upload.filing_period_id)
    client = session.get(Client, upload.client_id)
    if period is not None and client is not None:
        recompute_period(session, period, client)
    session.commit()


# --- Thread -------------------------------------------------------------------------------------


class BackgroundWorker:
    def __init__(
        self,
        settings: Settings,
        session_factory: sessionmaker[Session],
        storage: FileStorage,
        extract: Extractor | None = None,
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._storage = storage
        self._extract = extract
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="hacienda-worker", daemon=True)
        self._thread.start()
        logger.info("Worker iniciado. Intervalo: %ss.", self._settings.worker_poll_interval_seconds)

    def stop(self, timeout: float = 10.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)
            self._thread = None

    def run_once(self) -> bool:
        """One polling cycle. Returns True when it processed something."""
        timeout = self._settings.worker_run_timeout_minutes
        did_work = False
        with self._session_factory() as session:
            recover_stuck_runs(session, timeout)
            recover_stuck_extractions(session, timeout)

            upload_id = try_claim_extraction(session)
            if upload_id is not None:
                process_extraction(session, self._storage, self._settings, upload_id, extract=self._extract)
                did_work = True

            run_id = try_claim_run(session)
            if run_id is not None:
                process_run(session, self._storage, self._settings, run_id)
                did_work = True
        return did_work

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                if not self.run_once():
                    self._stop.wait(self._settings.worker_poll_interval_seconds)
            except Exception:
                logger.exception("Error inesperado en el worker.")
                self._stop.wait(5)
