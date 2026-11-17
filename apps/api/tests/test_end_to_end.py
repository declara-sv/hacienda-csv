"""Upload real sample PDFs through the real extraction and anexo modules.

The samples are private (not in git); the test is skipped when they are absent.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers import ApiUser, run_extractions, run_generations

SAMPLES = Path(__file__).parent / "fixtures" / "private"
FILES = ("factura_exentas_gravadas.pdf", "factura_gravadas.pdf")

pytestmark = [
    pytest.mark.real_integrations,
    pytest.mark.skipif(
        not all((SAMPLES / f).is_file() for f in FILES), reason="muestras privadas no disponibles"
    ),
]


def test_pdf_to_anexo2_csv(user: ApiUser, session_factory, storage, settings) -> None:
    assert settings.anthropic_api_key == ""
    from app.anexos import RENTA_CATALOG

    client_id = user.create_client(nit=None, nrc=None, defaultTipoOperacion=None, defaultTipoIngreso=None)
    period_id = user.create_period(client_id, 2026, 1)
    for name in FILES:
        response = user.upload(client_id, period_id, name, (SAMPLES / name).read_bytes())
        assert response.status_code == 201, response.text
    assert run_extractions(session_factory, storage, settings) == 2

    uploads = user.get(f"/api/clients/{client_id}/periods/{period_id}/uploads").json()
    assert [u["extractionStatus"] for u in uploads] == ["Completed", "Completed"]
    docs = user.documents(client_id, period_id)
    assert len(docs) == 2
    assert all(d["extractionMethod"] == "Parser" and d["anexo"] == 2 for d in docs)
    # Wrong period and no Renta codes yet.
    assert all(d["status"] == "Error" for d in docs)
    assert user.create_run(client_id, period_id).status_code == 400

    fecha = docs[0]["fechaEmision"]
    year, month = int(fecha[:4]), int(fecha[5:7])
    assert (
        user.put(
            f"/api/clients/{client_id}/periods/{period_id}", json={"year": year, "month": month}
        ).status_code
        == 200
    )
    response = user.put(
        f"/api/clients/{client_id}",
        json={
            "name": "Cliente real",
            "taxId": docs[0]["emisorNit"],
            "nit": docs[0]["emisorNit"],
            "nrc": docs[0]["emisorNrc"],
            "defaultTipoOperacion": RENTA_CATALOG["tipoOperacion"][0]["code"],
            "defaultTipoIngreso": RENTA_CATALOG["tipoIngreso"][0]["code"],
        },
    )
    assert response.status_code == 200, response.text

    docs = user.documents(client_id, period_id)
    assert [d["status"] for d in docs] != ["Error", "Error"], docs
    assert all(d["status"] != "Error" for d in docs), [d["issues"] for d in docs]

    run = user.create_run(client_id, period_id)
    assert run.status_code == 202, run.text
    assert run_generations(session_factory, storage, settings) == 1

    after = user.get(f"/api/clients/{client_id}/periods/{period_id}/runs/{run.json()['id']}").json()
    assert after["status"] == "Completed", after["errorMessage"]
    anexo2 = next(a for a in after["artifacts"] if a["fileName"].startswith("anexo2"))
    assert anexo2["rowCount"] == 2

    download = user.get(f"/api/artifacts/{anexo2['id']}/download")
    assert download.status_code == 200
    rows = [line for line in download.content.decode("cp1252").split("\r\n") if line]
    assert len(rows) == 2
