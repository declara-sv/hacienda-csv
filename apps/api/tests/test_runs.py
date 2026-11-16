from __future__ import annotations

import threading
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from app.models import GenerationRun, Upload
from tests.helpers import ApiUser, fake_pdf, record, run_extractions


@pytest.fixture
def extract(session_factory, storage, settings):
    return lambda: run_extractions(session_factory, storage, settings)


def runs_url(client_id: str, period_id: str) -> str:
    return f"/api/clients/{client_id}/periods/{period_id}/runs"


def ready_period(user: ApiUser, extract, *files: str) -> tuple[str, str]:
    client_id, period_id = user.setup_period()
    for name in files or ("a.pdf",):
        user.upload(client_id, period_id, name)
    extract()
    return client_id, period_id


def test_create_run_without_uploads_returns_400(user: ApiUser) -> None:
    client_id, period_id = user.setup_period()
    response = user.create_run(client_id, period_id)
    assert response.status_code == 400
    assert response.json()["errors"] == {"uploads": ["El período no tiene archivos para generar."]}


def test_create_run_while_extraction_pending_returns_409(user: ApiUser) -> None:
    client_id, period_id = user.setup_period()
    user.upload(client_id, period_id)
    response = user.create_run(client_id, period_id)
    assert response.status_code == 409
    assert "leyendo" in response.json()["title"]


def test_create_run_without_included_documents_returns_400(user: ApiUser, extract) -> None:
    client_id, period_id = user.setup_period()
    user.upload(client_id, period_id, "roto.pdf", content=b"%PDF basura")
    extract()
    response = user.create_run(client_id, period_id)
    assert response.status_code == 400
    assert response.json()["errors"] == {
        "documents": ["El período no tiene documentos incluidos para generar."]
    }


def test_create_run_with_document_errors_returns_400(user: ApiUser, extract) -> None:
    client_id, period_id = user.setup_period()
    user.upload(client_id, period_id, content=fake_pdf(record(), record(fecha_emision="2025-12-31")))
    extract()
    response = user.create_run(client_id, period_id)
    assert response.status_code == 400
    assert response.json()["errors"] == {
        "documents": ["1 documento tiene errores. Corríjalos o exclúyalos antes de generar."]
    }

    # Excluded documents keep their issues but no longer block.
    bad = next(d for d in user.documents(client_id, period_id) if d["status"] == "Error")
    user.patch(f"/api/clients/{client_id}/periods/{period_id}/documents/{bad['id']}", json={"excluded": True})
    assert user.create_run(client_id, period_id).status_code == 202
    still = next(d for d in user.documents(client_id, period_id) if d["id"] == bad["id"])
    assert still["status"] == "Error"


def test_create_run_snapshots_contributing_files_and_assigns_version(user: ApiUser, extract) -> None:
    client_id, period_id = user.setup_period()
    user.upload(client_id, period_id, "b.pdf")
    user.upload(client_id, period_id, "a.pdf")
    user.upload(client_id, period_id, "excluido.pdf")
    extract()
    excluded = next(
        d for d in user.documents(client_id, period_id) if d["originalFileName"] == "excluido.pdf"
    )
    user.patch(
        f"/api/clients/{client_id}/periods/{period_id}/documents/{excluded['id']}", json={"excluded": True}
    )

    response = user.create_run(client_id, period_id)
    assert response.status_code == 202
    run = response.json()
    assert response.headers["location"] == f"{runs_url(client_id, period_id)}/{run['id']}"
    assert run["version"] == 1
    assert run["status"] == "Pending"
    assert [f["originalFileName"] for f in run["files"]] == ["a.pdf", "b.pdf"]
    assert all(f["status"] == "Pending" and f["sourceFileKind"] == "PDF" for f in run["files"])
    assert run["artifacts"] == []
    assert run["issues"] == []
    assert run["startedAtUtc"] is None


def test_create_run_while_active_returns_409(user: ApiUser, extract) -> None:
    client_id, period_id = ready_period(user, extract)
    assert user.create_run(client_id, period_id).status_code == 202
    second = user.create_run(client_id, period_id)
    assert second.status_code == 409
    assert second.json()["title"] == "Ya existe una generación en curso para este período."


def test_concurrent_creates_yield_one_202_and_one_409(app, user: ApiUser, extract) -> None:
    client_id, period_id = ready_period(user, extract)
    results: list[int] = []
    barrier = threading.Barrier(2)

    def create() -> None:
        with TestClient(app) as http:
            barrier.wait()
            response = http.post(runs_url(client_id, period_id), headers=user.headers)
            results.append(response.status_code)

    threads = [threading.Thread(target=create) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == [202, 409]


def test_active_run_unique_index_rejects_second_pending_run(user: ApiUser, extract, db) -> None:
    client_id, period_id = ready_period(user, extract)
    run = user.create_run(client_id, period_id).json()
    original = db.get(GenerationRun, uuid.UUID(run["id"]))
    db.add(
        GenerationRun(
            client_id=original.client_id,
            filing_period_id=original.filing_period_id,
            requested_by_user_id=original.requested_by_user_id,
            version=2,
            status="Running",
            issues=[],
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_list_and_get_runs_newest_version_first(user: ApiUser, extract, db) -> None:
    client_id, period_id = ready_period(user, extract)
    first = user.create_run(client_id, period_id).json()
    db.execute(
        update(GenerationRun).where(GenerationRun.id == uuid.UUID(first["id"])).values(status="Failed")
    )
    db.commit()
    second = user.create_run(client_id, period_id).json()
    assert second["version"] == 2

    listed = user.get(runs_url(client_id, period_id)).json()
    assert [r["id"] for r in listed] == [second["id"], first["id"]]
    single = user.get(f"{runs_url(client_id, period_id)}/{first['id']}")
    assert single.status_code == 200 and single.json()["status"] == "Failed"
    assert user.get(f"{runs_url(client_id, period_id)}/{uuid.uuid4()}").status_code == 404


def test_status_serializes_as_string(user: ApiUser, extract) -> None:
    client_id, period_id = ready_period(user, extract)
    response = user.create_run(client_id, period_id)
    assert '"status":"Pending"' in response.text


def test_other_user_gets_404_on_runs(user: ApiUser, other_user: ApiUser, extract) -> None:
    client_id, period_id = ready_period(user, extract)
    run = user.create_run(client_id, period_id).json()
    url = runs_url(client_id, period_id)
    assert other_user.post(url).status_code == 404
    assert other_user.get(url).status_code == 404
    assert other_user.get(f"{url}/{run['id']}").status_code == 404


def test_upload_failed_extraction_does_not_block_runs(user: ApiUser, extract, db) -> None:
    client_id, period_id = ready_period(user, extract)
    broken = user.upload(client_id, period_id, "roto.pdf", content=b"basura").json()
    extract()
    assert db.get(Upload, uuid.UUID(broken["id"])).extraction_status == "Failed"
    run = user.create_run(client_id, period_id).json()
    assert [f["originalFileName"] for f in run["files"]] == ["a.pdf"]
