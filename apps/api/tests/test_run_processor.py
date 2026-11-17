from __future__ import annotations

import datetime as dt
import uuid

import pytest
from sqlalchemy import update

from app.models import GenerationRun
from app.services import integrations
from app.worker import (
    _CLAIM_RUN_SQL,
    CSV_CONTENT_TYPE,
    BackgroundWorker,
    recover_stuck_runs,
)
from tests.helpers import ApiUser, fake_pdf, record, run_extractions, run_generations


@pytest.fixture
def extract(session_factory, storage, settings):
    return lambda: run_extractions(session_factory, storage, settings)


@pytest.fixture
def generate(session_factory, storage, settings):
    return lambda: run_generations(session_factory, storage, settings)


def runs_url(client_id: str, period_id: str) -> str:
    return f"/api/clients/{client_id}/periods/{period_id}/runs"


def start_run(user: ApiUser, extract, *contents: bytes) -> tuple[str, str, dict]:
    client_id, period_id = user.setup_period()
    for i, content in enumerate(contents or (fake_pdf(record()),)):
        user.upload(client_id, period_id, f"f{i}.pdf", content)
    extract()
    response = user.create_run(client_id, period_id)
    assert response.status_code == 202, response.text
    return client_id, period_id, response.json()


def test_concurrent_claims_return_exactly_one_run(user: ApiUser, extract, session_factory) -> None:
    _, _, run = start_run(user, extract)
    with session_factory() as a, session_factory() as b:
        first = a.execute(_CLAIM_RUN_SQL).scalar_one_or_none()
        second = b.execute(_CLAIM_RUN_SQL).scalar_one_or_none()
        a.commit()
        b.commit()
    assert str(first) == run["id"]
    assert second is None


def test_stuck_running_run_is_failed_by_recovery(user: ApiUser, extract, db, session_factory) -> None:
    client_id, period_id, run = start_run(user, extract)
    db.execute(
        update(GenerationRun)
        .where(GenerationRun.id == uuid.UUID(run["id"]))
        .values(status="Running", started_at_utc=dt.datetime.now(dt.UTC) - dt.timedelta(minutes=30))
    )
    db.commit()
    with session_factory() as session:
        assert recover_stuck_runs(session, 10) == 1
    after = user.get(f"{runs_url(client_id, period_id)}/{run['id']}").json()
    assert after["status"] == "Failed"
    assert after["errorMessage"] == "La generación excedió el tiempo máximo de 10 minutos."
    assert after["completedAtUtc"] is not None


def test_recent_running_run_is_not_recovered(user: ApiUser, extract, db, session_factory) -> None:
    _, _, run = start_run(user, extract)
    db.execute(
        update(GenerationRun)
        .where(GenerationRun.id == uuid.UUID(run["id"]))
        .values(status="Running", started_at_utc=dt.datetime.now(dt.UTC))
    )
    db.commit()
    with session_factory() as session:
        assert recover_stuck_runs(session, 10) == 0


def test_processing_builds_artifacts_and_marks_files_included(user: ApiUser, extract, generate) -> None:
    client_id, period_id, run = start_run(
        user,
        extract,
        fake_pdf(record(fecha_emision="2026-01-02"), record(fecha_emision="2026-01-03")),
        fake_pdf(record(tipo_dte="03", fecha_emision="2026-01-03", iva="1.30")),
    )
    assert generate() == 1

    after = user.get(f"{runs_url(client_id, period_id)}/{run['id']}").json()
    assert after["status"] == "Completed"
    assert after["errorMessage"] is None
    assert after["startedAtUtc"] and after["completedAtUtc"]
    assert all(f["status"] == "Included" for f in after["files"])
    assert [(a["fileName"], a["rowCount"]) for a in after["artifacts"]] == [
        ("anexo1_202601.csv", 1),
        ("anexo2_202601.csv", 2),
    ]
    assert after["issues"] == [
        {
            "code": "FAKE_NOTE",
            "severity": "Warning",
            "message": "Generado con el builder falso.",
            "field": None,
        }
    ]

    anexo2 = after["artifacts"][1]
    download = user.get(f"/api/artifacts/{anexo2['id']}/download")
    assert download.status_code == 200
    assert download.headers["content-type"] == CSV_CONTENT_TYPE
    assert 'filename="anexo2_202601.csv"' in download.headers["content-disposition"]
    assert download.content.count(b"\r\n") == 2
    assert anexo2["sizeBytes"] == len(download.content)

    uploads = user.get(f"/api/clients/{client_id}/periods/{period_id}/uploads").json()
    assert all(u["includedInLatestRun"] for u in uploads)


def test_builder_failure_marks_run_failed(user: ApiUser, extract, generate, monkeypatch) -> None:
    client_id, period_id, run = start_run(user, extract)

    def boom(**kwargs):
        raise ValueError("Columna inválida en la especificación.")

    monkeypatch.setattr(integrations, "build_sales_anexos", boom)
    generate()
    after = user.get(f"{runs_url(client_id, period_id)}/{run['id']}").json()
    assert after["status"] == "Failed"
    assert after["errorMessage"] == "Columna inválida en la especificación."
    assert after["artifacts"] == []
    # A new run can be requested after a failure.
    assert user.create_run(client_id, period_id).json()["version"] == 2


def test_documents_excluded_after_run_creation_are_left_out(user: ApiUser, extract, generate) -> None:
    client_id, period_id, run = start_run(user, extract, fake_pdf(record()), fake_pdf(record()))
    docs = user.documents(client_id, period_id)
    for doc in docs:
        user.patch(
            f"/api/clients/{client_id}/periods/{period_id}/documents/{doc['id']}", json={"excluded": True}
        )
    generate()
    after = user.get(f"{runs_url(client_id, period_id)}/{run['id']}").json()
    assert after["status"] == "Failed"
    assert after["errorMessage"] == "No hay documentos incluidos para generar."


def test_upload_after_completed_run_is_not_included_in_latest_run(user: ApiUser, extract, generate) -> None:
    client_id, period_id, _ = start_run(user, extract)
    generate()
    user.upload(client_id, period_id, "later.pdf")
    extract()

    uploads = {
        u["originalFileName"]: u
        for u in user.get(f"/api/clients/{client_id}/periods/{period_id}/uploads").json()
    }
    assert uploads["later.pdf"]["includedInLatestRun"] is False
    assert uploads["f0.pdf"]["includedInLatestRun"] is True

    second = user.create_run(client_id, period_id).json()
    assert second["version"] == 2
    assert len(second["files"]) == 2


def test_other_user_cannot_download_artifact(user: ApiUser, other_user: ApiUser, extract, generate) -> None:
    client_id, period_id, run = start_run(user, extract)
    generate()
    artifact = user.get(f"{runs_url(client_id, period_id)}/{run['id']}").json()["artifacts"][0]
    assert other_user.get(f"/api/artifacts/{artifact['id']}/download").status_code == 404
    assert user.get(f"/api/artifacts/{uuid.uuid4()}/download").status_code == 404


def test_missing_artifact_file_is_404(user: ApiUser, extract, generate, storage_root) -> None:
    client_id, period_id, run = start_run(user, extract)
    generate()
    artifact = user.get(f"{runs_url(client_id, period_id)}/{run['id']}").json()["artifacts"][0]
    for path in (storage_root / "outputs").rglob("*.csv"):
        path.unlink()
    assert user.get(f"/api/artifacts/{artifact['id']}/download").status_code == 404


def test_background_worker_cycle_extracts_and_generates(
    user: ApiUser, settings, session_factory, storage
) -> None:
    client_id, period_id = user.setup_period()
    user.upload(client_id, period_id)
    worker = BackgroundWorker(settings, session_factory, storage)
    assert worker.run_once() is True
    assert user.documents(client_id, period_id)[0]["status"] == "Ok"

    run = user.create_run(client_id, period_id).json()
    assert worker.run_once() is True
    assert worker.run_once() is False
    after = user.get(f"{runs_url(client_id, period_id)}/{run['id']}").json()
    assert after["status"] == "Completed"


def test_worker_thread_starts_and_stops(settings, session_factory, storage) -> None:
    worker = BackgroundWorker(
        settings.model_copy(update={"worker_poll_interval_seconds": 0.05}), session_factory, storage
    )
    worker.start()
    worker.stop(timeout=5)
    assert worker._thread is None


def test_builder_errors_fail_the_run_and_keep_its_issues(
    user: ApiUser, extract, generate, monkeypatch
) -> None:
    from app.domain import AnexoBuildResult, Issue, IssueSeverity

    client_id, period_id, run = start_run(user, extract)
    issue = Issue(code="bad_nit", severity=IssueSeverity.ERROR, message="NIT del receptor inválido.")
    monkeypatch.setattr(
        integrations, "build_sales_anexos", lambda **kw: AnexoBuildResult(files=[], issues=[issue])
    )
    generate()
    after = user.get(f"{runs_url(client_id, period_id)}/{run['id']}").json()
    assert after["status"] == "Failed"
    assert after["errorMessage"] == "No se generaron los anexos: NIT del receptor inválido."
    assert [i["code"] for i in after["issues"]] == ["bad_nit"]
    assert after["artifacts"] == []
