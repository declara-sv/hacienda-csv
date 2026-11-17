from __future__ import annotations

import datetime as dt
import threading
import uuid

from sqlalchemy import select, update

from app.domain import ExtractionMethod, ExtractionResult
from app.models import DteDocument, ExtractionStatus, Upload
from app.worker import (
    EXCEL_NOT_SUPPORTED,
    process_extraction,
    recover_stuck_extractions,
    try_claim_extraction,
)
from tests.helpers import ApiUser, fake_pdf, record, run_extractions


def _upload(db, upload_id: str) -> Upload:
    db.expire_all()
    return db.get(Upload, uuid.UUID(upload_id))


def test_extraction_saves_documents_with_values_and_issues(
    user: ApiUser, db, session_factory, storage, settings
) -> None:
    client_id, period_id = user.setup_period()
    rec = record(total_exentas="5.00", total_gravadas="11.30", total="16.30")
    dto = user.upload(
        client_id,
        period_id,
        content=fake_pdf(
            rec,
            method="Ai",
            issues=[{"code": "AI_USED", "severity": "Warning", "message": "Leído con IA.", "field": None}],
        ),
    ).json()

    assert run_extractions(session_factory, storage, settings) == 1

    upload = _upload(db, dto["id"])
    assert upload.extraction_status == "Completed"
    assert upload.extraction_completed_at_utc is not None
    [doc] = db.scalars(select(DteDocument)).all()
    assert doc.extraction_method == "Ai"
    assert doc.codigo_generacion == rec["codigo_generacion"]
    assert str(doc.total) == "16.30"
    assert doc.extracted["codigo_generacion"] == rec["codigo_generacion"]
    assert doc.status == "Warning"
    assert [i["code"] for i in doc.issues] == ["AI_USED"]


def test_excel_upload_fails_with_message(user: ApiUser, db, session_factory, storage, settings) -> None:
    client_id, period_id = user.setup_period()
    dto = user.upload(client_id, period_id, "ventas.xlsx", content=b"PK..", kind="Excel").json()
    run_extractions(session_factory, storage, settings)
    upload = _upload(db, dto["id"])
    assert upload.extraction_status == "Failed"
    assert upload.extraction_error == EXCEL_NOT_SUPPORTED


def test_unreadable_pdf_and_empty_result_fail(user: ApiUser, db, session_factory, storage, settings) -> None:
    client_id, period_id = user.setup_period()
    broken = user.upload(client_id, period_id, "roto.pdf", content=b"%PDF-1.4 basura").json()
    empty = user.upload(
        client_id,
        period_id,
        "vacio.pdf",
        content=fake_pdf(
            issues=[{"code": "NO_TEXT", "severity": "Error", "message": "El PDF no tiene texto."}]
        ),
    ).json()
    run_extractions(session_factory, storage, settings)

    assert _upload(db, broken["id"]).extraction_status == "Failed"
    assert "PDF ilegible" in _upload(db, broken["id"]).extraction_error
    assert _upload(db, empty["id"]).extraction_error == "El PDF no tiene texto."

    listed = {
        u["originalFileName"]: u
        for u in user.get(f"/api/clients/{client_id}/periods/{period_id}/uploads").json()
    }
    assert listed["vacio.pdf"]["extractionStatus"] == "Failed"
    assert listed["vacio.pdf"]["extractionError"] == "El PDF no tiene texto."


def test_missing_storage_object_fails_extraction(
    user: ApiUser, db, session_factory, storage, settings, storage_root
) -> None:
    client_id, period_id = user.setup_period()
    dto = user.upload(client_id, period_id).json()
    upload = _upload(db, dto["id"])
    (storage_root / upload.storage_container / upload.storage_path).unlink()
    run_extractions(session_factory, storage, settings)
    assert _upload(db, dto["id"]).extraction_error == "No se encontró el archivo en el almacenamiento."


def test_concurrent_extraction_claims_return_one_upload(user: ApiUser, session_factory) -> None:
    client_id, period_id = user.setup_period()
    dto = user.upload(client_id, period_id).json()

    with session_factory() as a, session_factory() as b:
        from app.worker import _CLAIM_EXTRACTION_SQL

        first = a.execute(_CLAIM_EXTRACTION_SQL).scalar_one_or_none()  # row locked, not committed
        second = b.execute(_CLAIM_EXTRACTION_SQL).scalar_one_or_none()
        a.commit()
        b.commit()
    assert str(first) == dto["id"]
    assert second is None


def test_claims_from_threads_never_process_the_same_upload_twice(user: ApiUser, session_factory) -> None:
    client_id, period_id = user.setup_period()
    for i in range(6):
        user.upload(client_id, period_id, f"f{i}.pdf")

    claimed: list[uuid.UUID] = []
    lock = threading.Lock()

    def worker() -> None:
        with session_factory() as session:
            while (upload_id := try_claim_extraction(session)) is not None:
                with lock:
                    claimed.append(upload_id)

    threads = [threading.Thread(target=worker) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(claimed) == 6 and len(set(claimed)) == 6


def test_stuck_extraction_is_failed_by_recovery(user: ApiUser, db, session_factory) -> None:
    client_id, period_id = user.setup_period()
    dto = user.upload(client_id, period_id).json()
    db.execute(
        update(Upload)
        .where(Upload.id == uuid.UUID(dto["id"]))
        .values(
            extraction_status=ExtractionStatus.RUNNING.value,
            extraction_started_at_utc=dt.datetime.now(dt.UTC) - dt.timedelta(minutes=30),
        )
    )
    db.commit()
    with session_factory() as session:
        assert recover_stuck_extractions(session, 10) == 1
    upload = _upload(db, dto["id"])
    assert upload.extraction_status == "Failed"
    assert "excedió el tiempo máximo de 10 minutos" in upload.extraction_error


def test_result_is_discarded_when_upload_was_requeued_meanwhile(
    user: ApiUser, db, session_factory, storage, settings
) -> None:
    client_id, period_id = user.setup_period()
    dto = user.upload(client_id, period_id).json()

    with session_factory() as session:
        upload_id = try_claim_extraction(session)

        def slow_extract(data: bytes) -> ExtractionResult:
            # Meanwhile the run is recovered as stuck and re-queued by the user.
            with session_factory() as other:
                other.execute(
                    update(Upload)
                    .where(Upload.id == upload_id)
                    .values(extraction_status="Pending", extraction_started_at_utc=None)
                )
                other.commit()
            return ExtractionResult(method=ExtractionMethod.PARSER, records=[])

        process_extraction(session, storage, settings, upload_id, extract=slow_extract)

    upload = _upload(db, dto["id"])
    assert upload.extraction_status == "Pending"
    assert db.scalar(select(DteDocument.id)) is None


def test_multiple_records_in_one_pdf_create_one_document_each(
    user: ApiUser, session_factory, storage, settings
) -> None:
    client_id, period_id = user.setup_period()
    user.upload(client_id, period_id, content=fake_pdf(record(), record(), record()))
    run_extractions(session_factory, storage, settings)
    docs = user.documents(client_id, period_id)
    assert len(docs) == 3
    assert {d["originalFileName"] for d in docs} == {"factura.pdf"}
