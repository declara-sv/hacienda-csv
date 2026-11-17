from __future__ import annotations

import pytest

from tests.helpers import CLIENT_NIT, ApiUser, fake_pdf, record, run_extractions

DOCUMENT_KEYS = {
    "id",
    "uploadId",
    "originalFileName",
    "extractionMethod",
    "status",
    "issues",
    "edited",
    "excluded",
    "tipoDte",
    "codigoGeneracion",
    "numeroControl",
    "selloRecepcion",
    "fechaEmision",
    "horaEmision",
    "emisorNombre",
    "emisorNit",
    "emisorNrc",
    "receptorNombre",
    "receptorNit",
    "receptorNrc",
    "receptorDui",
    "totalNoSujetas",
    "totalExentas",
    "totalGravadas",
    "iva",
    "ivaRetenido",
    "total",
    "tipoOperacionRenta",
    "tipoIngresoRenta",
    "effectiveTipoOperacion",
    "effectiveTipoIngreso",
    "anexo",
}


@pytest.fixture
def extract(session_factory, storage, settings):
    return lambda: run_extractions(session_factory, storage, settings)


def docs_url(client_id: str, period_id: str) -> str:
    return f"/api/clients/{client_id}/periods/{period_id}/documents"


def test_list_documents_shape(user: ApiUser, extract) -> None:
    client_id, period_id = user.setup_period()
    rec = record(total_gravadas="48.1", total="48.14", iva="0.04", hora_emision="08:05:09")
    upload = user.upload(client_id, period_id, "f.pdf", fake_pdf(rec)).json()
    extract()

    [doc] = user.documents(client_id, period_id)
    assert set(doc) == DOCUMENT_KEYS
    assert doc["uploadId"] == upload["id"]
    assert doc["originalFileName"] == "f.pdf"
    assert doc["extractionMethod"] == "Parser"
    assert doc["status"] == "Ok" and doc["issues"] == []
    assert doc["edited"] is False and doc["excluded"] is False
    assert doc["fechaEmision"] == "2026-01-15"
    assert doc["horaEmision"] == "08:05:09"
    assert doc["totalGravadas"] == "48.10"
    assert doc["total"] == "48.14"
    assert doc["totalNoSujetas"] == "0.00"
    assert doc["tipoOperacionRenta"] is None
    assert doc["effectiveTipoOperacion"] == "1"
    assert doc["effectiveTipoIngreso"] == "3"
    assert doc["anexo"] == 2


def test_documents_ordered_by_date_and_time(user: ApiUser, extract) -> None:
    client_id, period_id = user.setup_period()
    user.upload(client_id, period_id, "b.pdf", fake_pdf(record(fecha_emision="2026-01-20")))
    user.upload(
        client_id,
        period_id,
        "a.pdf",
        fake_pdf(
            record(fecha_emision="2026-01-03", hora_emision="15:00:00"),
            record(fecha_emision="2026-01-03", hora_emision="09:00:00"),
        ),
    )
    extract()
    docs = user.documents(client_id, period_id)
    assert [(d["fechaEmision"], d["horaEmision"]) for d in docs] == [
        ("2026-01-03", "09:00:00"),
        ("2026-01-03", "15:00:00"),
        ("2026-01-20", "10:30:00"),
    ]


def test_issues_follow_client_defaults_and_period(user: ApiUser, extract) -> None:
    client_id, period_id = user.setup_period(defaultTipoOperacion=None, defaultTipoIngreso=None)
    user.upload(client_id, period_id, content=fake_pdf(record(), record(fecha_emision="2026-02-01")))
    extract()

    docs = user.documents(client_id, period_id)
    assert [d["status"] for d in docs] == ["Error", "Error"]
    assert {i["code"] for i in docs[0]["issues"]} == {"RENTA_REQUIRED"}
    assert {i["code"] for i in docs[1]["issues"]} == {"RENTA_REQUIRED", "OUT_OF_PERIOD"}

    # Editing the client recomputes stored issues.
    response = user.put(
        f"/api/clients/{client_id}",
        json={"name": "C", "taxId": "T", "defaultTipoOperacion": "1", "defaultTipoIngreso": "3"},
    )
    assert response.status_code == 200
    docs = user.documents(client_id, period_id)
    assert [d["status"] for d in docs] == ["Ok", "Error"]
    assert [i["code"] for i in docs[1]["issues"]] == ["OUT_OF_PERIOD"]
    assert docs[0]["effectiveTipoOperacion"] == "1"

    # Moving the period recomputes "fuera del período".
    user.put(f"/api/clients/{client_id}/periods/{period_id}", json={"year": 2026, "month": 2})
    docs = user.documents(client_id, period_id)
    assert [d["status"] for d in docs] == ["Error", "Ok"]


def test_duplicates_are_errors_until_one_is_excluded(user: ApiUser, extract) -> None:
    client_id, period_id = user.setup_period()
    rec = record()
    user.upload(client_id, period_id, "a.pdf", fake_pdf(rec))
    user.upload(client_id, period_id, "b.pdf", fake_pdf(rec))
    extract()

    docs = user.documents(client_id, period_id)
    assert [d["status"] for d in docs] == ["Error", "Error"]
    assert all(d["issues"][0]["code"] == "DUPLICATE" for d in docs)

    excluded = user.patch(f"{docs_url(client_id, period_id)}/{docs[1]['id']}", json={"excluded": True})
    assert excluded.status_code == 200
    assert excluded.json()["excluded"] is True
    assert excluded.json()["edited"] is False

    by_id = {d["id"]: d for d in user.documents(client_id, period_id)}
    assert by_id[docs[0]["id"]]["status"] == "Ok"
    assert by_id[docs[1]["id"]]["status"] == "Ok"


def test_patch_edits_fields_marks_edited_and_revalidates(user: ApiUser, extract) -> None:
    client_id, period_id = user.setup_period()
    user.upload(
        client_id,
        period_id,
        content=fake_pdf(
            record(codigo_generacion=None),
            issues=[{"code": "PARSER_GAP", "severity": "Warning", "message": "Campo faltante."}],
        ),
    )
    extract()
    [doc] = user.documents(client_id, period_id)
    assert doc["status"] == "Error"
    assert {i["code"] for i in doc["issues"]} == {"CODIGO_REQUIRED", "PARSER_GAP"}

    response = user.patch(
        f"{docs_url(client_id, period_id)}/{doc['id']}",
        json={
            "codigoGeneracion": " 11111111-2222-3333-4444-555555555555 ",
            "totalExentas": "1.5",
            "fechaEmision": "2026-01-31",
            "receptorNombre": "",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["edited"] is True
    assert body["codigoGeneracion"] == "11111111-2222-3333-4444-555555555555"
    assert body["totalExentas"] == "1.50"
    assert body["fechaEmision"] == "2026-01-31"
    assert body["receptorNombre"] is None
    # Extractor issues are dropped once the user edits the document.
    assert body["status"] == "Ok" and body["issues"] == []


def test_patch_renta_overrides_and_reset_to_client_default(user: ApiUser, extract) -> None:
    client_id, period_id = user.setup_period()
    user.upload(client_id, period_id)
    extract()
    [doc] = user.documents(client_id, period_id)
    url = f"{docs_url(client_id, period_id)}/{doc['id']}"

    body = user.patch(url, json={"tipoOperacionRenta": "2", "tipoIngresoRenta": "4"}).json()
    assert body["tipoOperacionRenta"] == "2" and body["effectiveTipoOperacion"] == "2"
    assert body["effectiveTipoIngreso"] == "4"

    body = user.patch(url, json={"tipoOperacionRenta": None}).json()
    assert body["tipoOperacionRenta"] is None
    assert body["effectiveTipoOperacion"] == "1"
    assert body["tipoIngresoRenta"] == "4"


def test_patch_validation(user: ApiUser, extract) -> None:
    client_id, period_id = user.setup_period()
    user.upload(client_id, period_id)
    extract()
    [doc] = user.documents(client_id, period_id)
    url = f"{docs_url(client_id, period_id)}/{doc['id']}"

    assert user.patch(url, json={"tipoOperacionRenta": "77"}).json()["errors"] == {
        "tipoOperacionRenta": ["El código no existe en el catálogo de Renta."]
    }
    assert user.patch(url, json={"tipoDte": "1"}).status_code == 400
    assert user.patch(url, json={"tipoDte": None}).status_code == 400
    assert user.patch(url, json={"total": None}).json()["errors"] == {"total": ["El campo es requerido."]}
    assert user.patch(url, json={"total": "-1"}).status_code == 400
    assert user.patch(url, json={"fechaEmision": "15/01/2026"}).json()["errors"] == {
        "fechaEmision": ["Fecha inválida (use AAAA-MM-DD)."]
    }
    assert user.patch(f"{docs_url(client_id, period_id)}/{period_id}", json={}).status_code == 404


def test_bulk_update_applies_changes_and_returns_period_list(user: ApiUser, extract) -> None:
    client_id, period_id = user.setup_period(defaultTipoOperacion=None, defaultTipoIngreso=None)
    user.upload(client_id, period_id, content=fake_pdf(record(), record(), record()))
    extract()
    docs = user.documents(client_id, period_id)
    assert all(d["status"] == "Error" for d in docs)
    targets = [docs[0]["id"], docs[1]["id"]]

    response = user.post(
        f"{docs_url(client_id, period_id)}/bulk",
        json={"documentIds": targets, "tipoOperacionRenta": "1", "tipoIngresoRenta": "3"},
    )
    assert response.status_code == 200
    by_id = {d["id"]: d for d in response.json()}
    assert len(by_id) == 3
    assert [by_id[i]["status"] for i in targets] == ["Ok", "Ok"]
    assert by_id[docs[2]["id"]]["status"] == "Error"

    excluded = user.post(
        f"{docs_url(client_id, period_id)}/bulk", json={"documentIds": [docs[2]["id"]], "excluded": True}
    ).json()
    assert {d["id"]: d["excluded"] for d in excluded}[docs[2]["id"]] is True


def test_bulk_validation(user: ApiUser, other_user: ApiUser, extract) -> None:
    client_id, period_id = user.setup_period()
    user.upload(client_id, period_id)
    extract()
    [doc] = user.documents(client_id, period_id)
    url = f"{docs_url(client_id, period_id)}/bulk"

    assert user.post(url, json={"documentIds": []}).status_code == 400
    no_changes = user.post(url, json={"documentIds": [doc["id"]]})
    assert no_changes.status_code == 400
    assert no_changes.json()["errors"] == {"changes": ["Indique al menos un cambio."]}

    other_client, other_period = other_user.setup_period()
    other_user.upload(other_client, other_period)
    extract()
    [foreign] = other_user.documents(other_client, other_period)
    response = user.post(url, json={"documentIds": [doc["id"], foreign["id"]], "excluded": True})
    assert response.status_code == 400
    assert response.json()["errors"] == {
        "documentIds": ["Uno o más documentos no pertenecen a este período."]
    }


def test_documents_of_other_users_are_404(user: ApiUser, other_user: ApiUser, extract) -> None:
    client_id, period_id = user.setup_period()
    user.upload(client_id, period_id)
    extract()
    [doc] = user.documents(client_id, period_id)
    url = docs_url(client_id, period_id)
    assert other_user.get(url).status_code == 404
    assert other_user.patch(f"{url}/{doc['id']}", json={"excluded": True}).status_code == 404
    assert (
        other_user.post(f"{url}/bulk", json={"documentIds": [doc["id"]], "excluded": True}).status_code == 404
    )


def test_emisor_must_be_the_client(user: ApiUser, extract) -> None:
    client_id, period_id = user.setup_period()
    user.upload(client_id, period_id, content=fake_pdf(record(emisor_nit="0000-000000-000-0")))
    extract()
    [doc] = user.documents(client_id, period_id)
    assert doc["status"] == "Error"
    assert doc["issues"][0]["code"] == "NOT_CLIENT_SALE"
    assert doc["emisorNit"] != CLIENT_NIT


def test_types_outside_sales_anexos_are_warnings(user: ApiUser, extract) -> None:
    client_id, period_id = user.setup_period()
    user.upload(client_id, period_id, content=fake_pdf(record(tipo_dte="14")))
    extract()
    [doc] = user.documents(client_id, period_id)
    assert doc["status"] == "Warning"
    assert doc["anexo"] is None


def test_renta_catalog(user: ApiUser, client) -> None:
    response = user.get("/api/catalogs/renta")
    assert response.status_code == 200
    body = response.json()
    assert body["tipoOperacion"][0] == {"code": "1", "label": "Gravada"}
    assert client.get("/api/catalogs/renta").status_code == 401


def test_validator_crash_is_reported_as_document_error(user: ApiUser, extract, monkeypatch) -> None:
    from app.services import integrations

    client_id, period_id = user.setup_period()
    user.upload(client_id, period_id)
    extract()

    def broken(record):
        raise KeyError("bug")

    monkeypatch.setattr(integrations, "validate_record", broken)
    [doc] = user.documents(client_id, period_id)
    assert doc["status"] == "Error"
    assert doc["issues"][0]["code"] == "VALIDATION_FAILED"
