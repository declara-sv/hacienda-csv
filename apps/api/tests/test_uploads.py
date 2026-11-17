from __future__ import annotations

import hashlib
import uuid

from sqlalchemy import select, update

from app.models import ExtractionStatus, GenerationRun, Upload
from tests.helpers import ApiUser, fake_pdf, record, run_extractions


def uploads_url(client_id: str, period_id: str) -> str:
    return f"/api/clients/{client_id}/periods/{period_id}/uploads"


def test_upload_creates_pending_upload_and_no_run(user: ApiUser, db) -> None:
    client_id, period_id = user.setup_period()
    content = fake_pdf(record())
    response = user.upload(client_id, period_id, "factura.pdf", content)
    assert response.status_code == 201
    dto = response.json()
    assert response.headers["location"] == f"{uploads_url(client_id, period_id)}/{dto['id']}"
    assert dto["originalFileName"] == "factura.pdf"
    assert dto["sourceFileKind"] == "PDF"
    assert dto["contentType"] == "application/pdf"
    assert dto["sizeBytes"] == len(content)
    assert dto["includedInLatestRun"] is False
    assert dto["extractionStatus"] == "Pending"
    assert dto["extractionError"] is None
    assert dto["documentsCount"] == 0

    upload = db.get(Upload, uuid.UUID(dto["id"]))
    assert upload.sha256 == hashlib.sha256(content).hexdigest()
    assert db.scalar(select(GenerationRun.id)) is None


def test_list_returns_uploads_newest_first_with_document_counts(
    user: ApiUser, session_factory, storage, settings
) -> None:
    client_id, period_id = user.setup_period()
    user.upload(client_id, period_id, "a.pdf", fake_pdf(record(), record()))
    user.upload(client_id, period_id, "b.pdf")
    run_extractions(session_factory, storage, settings)

    uploads = user.get(uploads_url(client_id, period_id)).json()
    assert [u["originalFileName"] for u in uploads] == ["b.pdf", "a.pdf"]
    assert [u["documentsCount"] for u in uploads] == [1, 2]
    assert all(u["extractionStatus"] == "Completed" for u in uploads)


def test_upload_validation(user: ApiUser, settings) -> None:
    client_id, period_id = user.setup_period()

    wrong_kind = user.upload(client_id, period_id, "a.pdf", kind="Word")
    assert wrong_kind.status_code == 400
    assert wrong_kind.json()["errors"] == {"sourceFileKind": ["El tipo debe ser Excel o PDF."]}

    mismatch = user.upload(client_id, period_id, "a.xlsx", kind="PDF")
    assert mismatch.status_code == 400
    assert mismatch.json()["errors"]["file"] == [
        "El tipo de archivo no corresponde al tipo seleccionado (Excel/PDF)."
    ]

    empty = user.upload(client_id, period_id, "a.pdf", content=b"")
    assert empty.status_code == 400
    assert empty.json()["errors"]["file"] == ["El archivo está vacío."]

    missing_file = user.post(uploads_url(client_id, period_id), data={"sourceFileKind": "PDF"})
    assert missing_file.status_code == 400
    assert "file" in missing_file.json()["errors"]


def test_upload_over_size_limit_is_413(user: ApiUser, settings) -> None:
    client_id, period_id = user.setup_period()
    settings.max_upload_bytes = 1_000_000
    response = user.upload(client_id, period_id, "big.pdf", content=b"%PDF" + b"0" * 1_000_000)
    assert response.status_code == 413
    assert response.json()["title"] == "El archivo excede el tamaño máximo de 1 MB."


def test_delete_removes_row_and_storage_object(user: ApiUser, db, storage_root) -> None:
    client_id, period_id = user.setup_period()
    dto = user.upload(client_id, period_id).json()
    upload = db.get(Upload, uuid.UUID(dto["id"]))
    stored = storage_root / upload.storage_container / upload.storage_path
    assert stored.is_file()

    response = user.delete(f"{uploads_url(client_id, period_id)}/{dto['id']}")
    assert response.status_code == 204
    assert not stored.exists()
    db.expire_all()
    assert db.get(Upload, uuid.UUID(dto["id"])) is None


def test_delete_returns_409_when_referenced_by_active_run(
    user: ApiUser, session_factory, storage, settings
) -> None:
    client_id, period_id = user.setup_period()
    dto = user.upload(client_id, period_id).json()
    run_extractions(session_factory, storage, settings)
    assert user.create_run(client_id, period_id).status_code == 202

    response = user.delete(f"{uploads_url(client_id, period_id)}/{dto['id']}")
    assert response.status_code == 409
    assert response.json()["title"] == "El archivo está siendo usado por una generación en curso."

    reextract = user.post(f"{uploads_url(client_id, period_id)}/{dto['id']}/reextract")
    assert reextract.status_code == 409


def test_reextract_resets_extraction_and_deletes_documents(
    user: ApiUser, session_factory, storage, settings
) -> None:
    client_id, period_id = user.setup_period()
    dto = user.upload(client_id, period_id).json()
    run_extractions(session_factory, storage, settings)
    assert len(user.documents(client_id, period_id)) == 1

    response = user.post(f"{uploads_url(client_id, period_id)}/{dto['id']}/reextract")
    assert response.status_code == 200
    body = response.json()
    assert body["extractionStatus"] == "Pending"
    assert body["documentsCount"] == 0
    assert user.documents(client_id, period_id) == []

    run_extractions(session_factory, storage, settings)
    assert len(user.documents(client_id, period_id)) == 1


def test_reextract_while_running_is_409(user: ApiUser, db) -> None:
    client_id, period_id = user.setup_period()
    dto = user.upload(client_id, period_id).json()
    db.execute(
        update(Upload)
        .where(Upload.id == uuid.UUID(dto["id"]))
        .values(extraction_status=ExtractionStatus.RUNNING.value)
    )
    db.commit()
    response = user.post(f"{uploads_url(client_id, period_id)}/{dto['id']}/reextract")
    assert response.status_code == 409


def test_other_user_gets_404_on_uploads(user: ApiUser, other_user: ApiUser) -> None:
    client_id, period_id = user.setup_period()
    dto = user.upload(client_id, period_id).json()
    url = uploads_url(client_id, period_id)
    assert other_user.get(url).status_code == 404
    assert other_user.upload(client_id, period_id).status_code == 404
    assert other_user.delete(f"{url}/{dto['id']}").status_code == 404
    assert other_user.post(f"{url}/{dto['id']}/reextract").status_code == 404
    # Right owner, wrong period.
    other_period = user.create_period(client_id, 2026, 2)
    assert user.delete(f"{uploads_url(client_id, other_period)}/{dto['id']}").status_code == 404
