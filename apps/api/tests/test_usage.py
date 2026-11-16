"""Usage ledger: events at each write point, survival after deletes, pricing and the monthly report."""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.domain import AiUsage
from app.extraction import extract_pdf
from app.models import Account, UsageEvent
from app.usage import pricing, recorder
from app.usage.recorder import UsageScope
from app.worker import process_extraction, try_claim_extraction
from tests.extraction.support import FakeAi, build_pdf, drop_words, load_pages, make_record
from tests.helpers import ApiUser, fake_pdf, record, run_extractions, run_generations


def _events(db, event_type: str | None = None) -> list[UsageEvent]:
    db.expire_all()
    query = select(UsageEvent).order_by(UsageEvent.occurred_at_utc, UsageEvent.id)
    if event_type is not None:
        query = query.where(UsageEvent.event_type == event_type)
    return list(db.scalars(query))


def _user_id(user: ApiUser) -> uuid.UUID:
    return uuid.UUID(user.auth["user"]["id"])


def _account_id(user: ApiUser) -> uuid.UUID:
    return uuid.UUID(user.auth["user"]["account"]["id"])


def _ai_call(model: str = "claude-opus-5-5", outcome: str = "used", **tokens) -> dict:
    data = {"model": model, "input_tokens": 10_000, "output_tokens": 2_000, "outcome": outcome}
    data.update(tokens)
    return data


def _generate(user: ApiUser, session_factory, storage, settings) -> tuple[str, str, dict]:
    client_id, period_id = user.setup_period(name="Farmacia Uno")
    assert user.upload(client_id, period_id, content=fake_pdf(record(), record())).status_code == 201
    run_extractions(session_factory, storage, settings)
    assert user.create_run(client_id, period_id).status_code == 202
    run_generations(session_factory, storage, settings)
    (run,) = user.get(f"/api/clients/{client_id}/periods/{period_id}/runs").json()
    assert run["status"] == "Completed"
    return client_id, period_id, run


# --- Pricing ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        # 1M input + 1M output + 1M cache read + 1M cache write.
        ("claude-opus-5-5", Decimal("29.200000")),
        ("claude-sonnet-5-5", Decimal("14.600000")),
        ("claude-haiku-5-5", Decimal("0.735000")),
    ],
)
def test_cost_of_one_million_tokens_of_each_kind(model: str, expected: Decimal) -> None:
    million = 1_000_000
    cost = pricing.cost_usd(
        model,
        input_tokens=million,
        output_tokens=million,
        cache_read_tokens=million,
        cache_creation_tokens=million,
    )
    assert cost == expected


def test_cost_is_rounded_to_six_decimals() -> None:
    # 1234 * 4 / 1e6 + 567 * 20 / 1e6 = 0.004936 + 0.01134
    assert pricing.cost_usd("claude-opus-5-5", input_tokens=1234, output_tokens=567) == Decimal("0.016276")
    # 3 * 0.10 / 1e6 = 0.0000003 -> 0.000000
    assert pricing.cost_usd("claude-haiku-5-5", input_tokens=3, output_tokens=0) == Decimal("0.000000")


def test_unknown_model_or_missing_tokens_have_no_cost() -> None:
    assert pricing.cost_usd("gpt-5", input_tokens=100, output_tokens=100) is None
    assert pricing.cost_usd(None, input_tokens=100, output_tokens=100) is None
    assert pricing.cost_usd("claude-opus-5-5", input_tokens=None, output_tokens=None) is None
    assert pricing.PRICE_VERSION == "2026-11"


# --- Write points -------------------------------------------------------------------------------


def test_upload_records_upload_stored(user: ApiUser, db) -> None:
    client_id, period_id = user.setup_period(name="Farmacia Uno")
    content = fake_pdf(record())
    upload = user.upload(client_id, period_id, content=content).json()

    (event,) = _events(db)
    assert event.event_type == "upload_stored"
    assert event.bytes == len(content)
    assert event.account_id == _account_id(user)
    assert event.actor_user_id == _user_id(user)
    assert (str(event.client_id), event.client_name) == (client_id, "Farmacia Uno")
    assert str(event.filing_period_id) == period_id
    assert str(event.upload_id) == upload["id"]
    assert event.metadata_ == {"sourceFileKind": "PDF"}


def test_rejected_upload_records_nothing(user: ApiUser, db) -> None:
    client_id, period_id = user.setup_period()
    assert user.upload(client_id, period_id, file_name="x.txt").status_code == 400
    assert _events(db) == []


def test_parser_extraction_records_extraction_completed(
    user: ApiUser, db, session_factory, storage, settings
) -> None:
    client_id, period_id = user.setup_period()
    user.upload(client_id, period_id, content=fake_pdf(record(), record(), page_count=3))
    run_extractions(session_factory, storage, settings)

    (event,) = _events(db, "extraction_completed")
    assert event.extraction_method == "Parser"
    assert (event.documents, event.pages) == (2, 3)
    assert event.duration_ms is not None and event.duration_ms >= 0
    assert event.actor_user_id == _user_id(user)
    assert _events(db, "ai_call") == []


def test_ai_extraction_records_priced_ai_call(user: ApiUser, db, session_factory, storage, settings) -> None:
    client_id, period_id = user.setup_period()
    calls = [_ai_call(cache_read_tokens=1_000, cache_creation_tokens=500, duration_ms=1234)]
    user.upload(client_id, period_id, content=fake_pdf(record(), method="Ai", ai_calls=calls))
    run_extractions(session_factory, storage, settings)

    (completed,) = _events(db, "extraction_completed")
    assert completed.extraction_method == "Ai"
    (call,) = _events(db, "ai_call")
    assert call.ai_model == "claude-opus-5-5"
    assert (call.ai_input_tokens, call.ai_output_tokens) == (10_000, 2_000)
    assert (call.ai_cache_read_tokens, call.ai_cache_creation_tokens) == (1_000, 500)
    # 10k*4 + 2k*20 + 1k*0.2 + 500*5 = 40000 + 40000 + 200 + 2500 = 82700 / 1e6
    assert call.cost_usd == Decimal("0.082700")
    assert call.price_version == "2026-11"
    assert call.duration_ms == 1234
    assert call.metadata_ == {"outcome": "used"}
    assert call.upload_id == completed.upload_id


def test_unknown_model_call_keeps_tokens_without_cost(
    user: ApiUser, db, session_factory, storage, settings
) -> None:
    client_id, period_id = user.setup_period()
    calls = [_ai_call(model="claude-nuevo")]
    user.upload(client_id, period_id, content=fake_pdf(record(), method="Ai", ai_calls=calls))
    run_extractions(session_factory, storage, settings)

    (call,) = _events(db, "ai_call")
    assert call.ai_input_tokens == 10_000
    assert call.cost_usd is None and call.price_version is None


def _pdf_without_totals() -> bytes:
    page = drop_words(load_pages("factura_gravadas.json")[0], lambda w: 535 < w.top < 670)
    return build_pdf([page])


def test_discarded_ai_result_still_records_tokens_and_cost(
    user: ApiUser, db, session_factory, storage, settings
) -> None:
    """Real pipeline: the parser result is kept, but the AI call was billed and must be recorded."""
    client_id, period_id = user.setup_period()
    user.upload(client_id, period_id, content=_pdf_without_totals())
    bad = make_record(codigo_generacion="x", numero_control="y", total=Decimal("1.00"), emisor_nit=None)
    ai = FakeAi([bad], input_tokens=3_000, output_tokens=400)

    with session_factory() as session:
        upload_id = try_claim_extraction(session)
        process_extraction(
            session, storage, settings, upload_id, extract=lambda data: extract_pdf(data, ai=ai)
        )

    assert ai.calls == 1
    (completed,) = _events(db, "extraction_completed")
    assert (completed.extraction_method, completed.pages, completed.documents) == ("Parser", 1, 1)
    (call,) = _events(db, "ai_call")
    assert call.metadata_ == {"outcome": "discarded"}
    assert (call.ai_input_tokens, call.ai_output_tokens) == (3_000, 400)
    assert call.cost_usd == Decimal("0.020000")  # 3000*4 + 400*20 = 20000 / 1e6


def test_failed_extraction_records_error_and_failed_ai_call(
    user: ApiUser, db, session_factory, storage, settings
) -> None:
    client_id, period_id = user.setup_period()
    content = fake_pdf(
        method="Parser",
        issues=[{"code": "pdf_unreadable", "severity": "Error", "message": "No se pudo leer el PDF."}],
        ai_calls=[{"model": "claude-opus-5-5", "outcome": "failed"}],
        page_count=1,
    )
    user.upload(client_id, period_id, content=content)
    run_extractions(session_factory, storage, settings)

    (failed,) = _events(db, "extraction_failed")
    assert failed.metadata_ == {"error": "No se pudo leer el PDF."}
    assert (failed.pages, failed.documents) == (1, 0)
    (call,) = _events(db, "ai_call")
    assert call.metadata_ == {"outcome": "failed"}
    assert call.ai_input_tokens is None and call.cost_usd is None
    assert _events(db, "extraction_completed") == []


def test_unreadable_file_records_extraction_failed(
    user: ApiUser, db, session_factory, storage, settings
) -> None:
    client_id, period_id = user.setup_period()
    user.upload(client_id, period_id, content=b"%PDF basura")
    run_extractions(session_factory, storage, settings)
    (failed,) = _events(db, "extraction_failed")
    assert failed.extraction_method is None
    assert "PDF ilegible" in failed.metadata_["error"]


def test_reextraction_records_new_events(user: ApiUser, db, session_factory, storage, settings) -> None:
    client_id, period_id = user.setup_period()
    content = fake_pdf(record(), method="Ai", ai_calls=[_ai_call()])
    upload = user.upload(client_id, period_id, content=content).json()
    run_extractions(session_factory, storage, settings)
    url = f"/api/clients/{client_id}/periods/{period_id}/uploads/{upload['id']}/reextract"
    assert user.post(url).status_code == 200
    run_extractions(session_factory, storage, settings)

    assert len(_events(db, "extraction_completed")) == 2
    assert len(_events(db, "ai_call")) == 2
    assert len(_events(db, "upload_stored")) == 1


def test_ai_calls_are_recorded_when_upload_is_deleted_during_extraction(
    user: ApiUser, db, session_factory, storage, settings
) -> None:
    client_id, period_id = user.setup_period(name="Farmacia Uno")
    upload = user.upload(client_id, period_id).json()

    def extract_then_delete(data: bytes):
        assert user.delete(f"/api/clients/{client_id}/periods/{period_id}/uploads/{upload['id']}").status_code
        from app.domain import ExtractionResult

        return ExtractionResult.model_validate_json(
            fake_pdf(record(), method="Ai", ai_calls=[_ai_call()]).decode()
        )

    with session_factory() as session:
        upload_id = try_claim_extraction(session)
        process_extraction(session, storage, settings, upload_id, extract=extract_then_delete)

    (call,) = _events(db, "ai_call")
    assert call.metadata_ == {"outcome": "discarded", "resultDropped": "upload_changed"}
    assert call.client_name == "Farmacia Uno"
    assert call.cost_usd == Decimal("0.080000")
    assert _events(db, "extraction_completed") == []


def test_run_and_download_record_events(user: ApiUser, db, session_factory, storage, settings) -> None:
    client_id, period_id, run = _generate(user, session_factory, storage, settings)

    (completed,) = _events(db, "run_completed")
    assert str(completed.run_id) == run["id"]
    assert completed.actor_user_id == _user_id(user)
    assert completed.documents == 2
    assert completed.rows == sum(a["rowCount"] for a in run["artifacts"])
    assert completed.bytes == sum(a["sizeBytes"] for a in run["artifacts"])
    assert completed.metadata_ == {"files": len(run["artifacts"]), "version": 1}

    artifact = run["artifacts"][0]
    response = user.get(f"/api/artifacts/{artifact['id']}/download")
    assert response.status_code == 200
    (download,) = _events(db, "artifact_downloaded")
    assert str(download.artifact_id) == artifact["id"]
    assert str(download.run_id) == run["id"]
    assert download.bytes == artifact["sizeBytes"] == len(response.content)
    assert download.actor_user_id == _user_id(user)
    assert download.metadata_ == {"fileName": artifact["fileName"]}


def test_foreign_download_records_nothing(
    user: ApiUser, other_user: ApiUser, db, session_factory, storage, settings
) -> None:
    _, _, run = _generate(user, session_factory, storage, settings)
    assert other_user.get(f"/api/artifacts/{run['artifacts'][0]['id']}/download").status_code == 404
    assert _events(db, "artifact_downloaded") == []


def test_events_survive_deleting_the_upload_and_the_client(
    user: ApiUser, db, session_factory, storage, settings
) -> None:
    client_id, period_id = user.setup_period(name="Farmacia Uno")
    upload = user.upload(client_id, period_id, content=fake_pdf(record(), ai_calls=[_ai_call()])).json()
    run_extractions(session_factory, storage, settings)
    before = len(_events(db))
    assert before == 3  # upload_stored, ai_call, extraction_completed

    url = f"/api/clients/{client_id}/periods/{period_id}/uploads/{upload['id']}"
    assert user.delete(url).status_code == 204
    assert len(_events(db)) == before
    assert user.delete(f"/api/clients/{client_id}").status_code == 204
    events = _events(db)
    assert len(events) == before
    assert {e.client_name for e in events} == {"Farmacia Uno"}


def test_recording_failure_does_not_break_the_upload(user: ApiUser, db, monkeypatch) -> None:
    client_id, period_id = user.setup_period()
    real = recorder.UsageEvent

    def broken_event(**fields):
        fields["event_type"] = "x" * 100  # longer than the column: the insert fails
        return real(**fields)

    monkeypatch.setattr(recorder, "UsageEvent", broken_event)
    response = user.upload(client_id, period_id)
    assert response.status_code == 201
    assert len(user.get(f"/api/clients/{client_id}/periods/{period_id}/uploads").json()) == 1
    assert _events(db) == []


def test_recorder_helpers_write_in_the_callers_transaction(user: ApiUser, db) -> None:
    scope = UsageScope(account_id=_account_id(user), actor_user_id=_user_id(user))
    recorder.ai_calls(db, scope, [AiUsage(model="claude-haiku-5-5", input_tokens=1_000, output_tokens=1_000)])
    db.rollback()
    assert db.scalar(select(func.count()).select_from(UsageEvent)) == 0


# --- Monthly report -----------------------------------------------------------------------------


def _now_month() -> tuple[int, int]:
    now = dt.datetime.now(dt.UTC)
    return now.year, now.month


def test_usage_report_aggregates_per_client_and_total(
    user: ApiUser, other_user: ApiUser, db, session_factory, storage, settings
) -> None:
    client_a, period_a = user.setup_period(name="Alfa")
    client_b, period_b = user.setup_period(name="Beta")
    pdf_a = fake_pdf(record(), record(), method="Ai", ai_calls=[_ai_call(), _ai_call(outcome="discarded")])
    pdf_b = fake_pdf(
        record(), method="Parser", ai_calls=[_ai_call(model="claude-nuevo", outcome="discarded")]
    )
    user.upload(client_a, period_a, content=pdf_a)
    user.upload(client_b, period_b, content=pdf_b)
    user.upload(client_b, period_b, content=fake_pdf(record()))
    run_extractions(session_factory, storage, settings)
    assert user.create_run(client_b, period_b).status_code == 202
    run_generations(session_factory, storage, settings)
    (run,) = user.get(f"/api/clients/{client_b}/periods/{period_b}/runs").json()
    user.get(f"/api/artifacts/{run['artifacts'][0]['id']}/download")
    user.get(f"/api/artifacts/{run['artifacts'][0]['id']}/download")

    # Noise: another account, and the same account in another month.
    other_client, other_period = other_user.setup_period(name="Ajeno")
    other_user.upload(other_client, other_period)
    db.add(
        UsageEvent(
            event_type="upload_stored",
            account_id=_account_id(user),
            client_id=uuid.UUID(client_a),
            client_name="Alfa",
            bytes=999,
            occurred_at_utc=dt.datetime(2020, 1, 15, tzinfo=dt.UTC),
        )
    )
    db.commit()

    year, month = _now_month()
    response = user.get(f"/api/usage?year={year}&month={month}")
    assert response.status_code == 200
    body = response.json()
    assert (body["year"], body["month"]) == (year, month)
    alfa, beta = body["clients"]
    assert (alfa["clientId"], alfa["clientName"]) == (client_a, "Alfa")
    assert alfa["uploads"] == 1
    assert alfa["bytesStored"] == len(pdf_a)
    assert alfa["documentsExtracted"] == {"parser": 0, "ai": 2, "manual": 0, "total": 2}
    assert alfa["aiCalls"] == 2
    assert (alfa["aiInputTokens"], alfa["aiOutputTokens"]) == (20_000, 4_000)
    assert alfa["aiCostUsd"] == "0.160000"
    assert alfa["aiCallsUnpriced"] == 0
    assert (alfa["runs"], alfa["downloads"]) == (0, 0)

    assert beta["clientName"] == "Beta"
    assert beta["uploads"] == 2
    assert beta["documentsExtracted"] == {"parser": 2, "ai": 0, "manual": 0, "total": 2}
    assert beta["aiCalls"] == 1
    assert beta["aiCostUsd"] == "0.000000"
    assert beta["aiCallsUnpriced"] == 1
    assert beta["runs"] == 1
    assert beta["rowsGenerated"] == run["artifacts"][0]["rowCount"]
    assert beta["downloads"] == 2

    total = body["total"]
    assert total["clientId"] is None and total["clientName"] is None
    assert total["uploads"] == 3
    assert total["bytesStored"] == alfa["bytesStored"] + beta["bytesStored"]
    assert total["documentsExtracted"]["total"] == 4
    assert total["aiCalls"] == 3
    assert total["aiInputTokens"] == 30_000
    assert total["aiCostUsd"] == "0.160000"
    assert (total["runs"], total["downloads"]) == (1, 2)

    old = user.get("/api/usage?year=2020&month=1").json()
    assert old["total"]["uploads"] == 1 and old["total"]["bytesStored"] == 999

    other = other_user.get(f"/api/usage?year={year}&month={month}").json()
    assert [c["clientName"] for c in other["clients"]] == ["Ajeno"]
    assert other["total"]["uploads"] == 1


def test_usage_report_keeps_deleted_and_renamed_clients(
    user: ApiUser, session_factory, storage, settings
) -> None:
    client_id, period_id = user.setup_period(name="Nombre viejo")
    user.upload(client_id, period_id)
    response = user.put(f"/api/clients/{client_id}", json={"name": "Nombre nuevo", "taxId": "X"})
    assert response.status_code == 200
    user.upload(client_id, period_id)
    assert user.delete(f"/api/clients/{client_id}").status_code == 204

    year, month = _now_month()
    (row,) = user.get(f"/api/usage?year={year}&month={month}").json()["clients"]
    assert (row["clientId"], row["clientName"], row["uploads"]) == (client_id, "Nombre nuevo", 2)


def test_usage_report_requires_auth_and_valid_month(client, user: ApiUser) -> None:
    assert client.get("/api/usage?year=2026&month=1").status_code == 401
    response = user.get("/api/usage?year=2026&month=13")
    assert response.status_code == 400
    assert "month" in response.json()["errors"]
    empty = user.get("/api/usage?year=2026&month=1").json()
    assert empty["clients"] == []
    assert empty["total"]["aiCostUsd"] == "0.000000"


def test_usage_report_honours_the_account_header(user: ApiUser, other_user: ApiUser, db) -> None:
    client_id, period_id = user.setup_period(name="Firma")
    user.upload(client_id, period_id)
    year, month = _now_month()
    foreign = {**other_user.headers, "X-Account-Id": str(_account_id(user))}
    assert other_user.http.get(f"/api/usage?year={year}&month={month}", headers=foreign).status_code == 403
    assert db.get(Account, _account_id(user)) is not None
