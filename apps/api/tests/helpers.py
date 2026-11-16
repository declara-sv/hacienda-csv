from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.storage import FileStorage
from app.worker import process_extraction, process_run, try_claim_extraction, try_claim_run

PASSWORD = "Password123!"
CLIENT_NIT = "0614-010101-101-1"
CLIENT_NRC = "123456-7"


def record(**overrides: Any) -> dict[str, Any]:
    """A valid Factura (01) of January 2026 issued by the default test client."""
    base: dict[str, Any] = {
        "tipo_dte": "01",
        "codigo_generacion": str(uuid.uuid4()).upper(),
        "numero_control": "DTE-01-M001P001-000000000000001",
        "sello_recepcion": "2026ABCDEF0123456789",
        "fecha_emision": "2026-01-15",
        "hora_emision": "10:30:00",
        "emisor_nombre": "EMPRESA DEMO, S.A. DE C.V.",
        "emisor_nit": CLIENT_NIT,
        "emisor_nrc": CLIENT_NRC,
        "receptor_nombre": "CONSUMIDOR FINAL",
        "total_gravadas": "11.30",
        "total": "11.30",
    }
    base.update(overrides)
    return base


def fake_pdf(
    *records: dict[str, Any],
    method: str = "Parser",
    issues: list[dict] | None = None,
    ai_calls: list[dict] | None = None,
    page_count: int | None = None,
) -> bytes:
    """Bytes understood by the fake extractor in tests/fakes.py."""
    payload = {
        "method": method,
        "records": list(records),
        "issues": issues or [],
        "ai_calls": ai_calls or [],
        "page_count": page_count,
    }
    return json.dumps(payload).encode()


class ApiUser:
    def __init__(self, client: TestClient, auth: dict[str, Any]) -> None:
        self.http = client
        self.auth = auth
        self.headers = {"Authorization": f"Bearer {auth['accessToken']}"}

    @classmethod
    def register(cls, client: TestClient, email: str | None = None) -> ApiUser:
        email = email or f"user-{uuid.uuid4().hex}@test.local"
        response = client.post(
            "/api/auth/register", json={"email": email, "password": PASSWORD, "fullName": "Test User"}
        )
        assert response.status_code == 201, response.text
        return cls(client, response.json())

    # --- raw verbs ---
    def get(self, url: str, **kw: Any) -> Response:
        return self.http.get(url, headers=self.headers, **kw)

    def post(self, url: str, **kw: Any) -> Response:
        return self.http.post(url, headers=self.headers, **kw)

    def put(self, url: str, **kw: Any) -> Response:
        return self.http.put(url, headers=self.headers, **kw)

    def patch(self, url: str, **kw: Any) -> Response:
        return self.http.patch(url, headers=self.headers, **kw)

    def delete(self, url: str, **kw: Any) -> Response:
        return self.http.delete(url, headers=self.headers, **kw)

    # --- shortcuts ---
    def create_client(self, **overrides: Any) -> str:
        body = {
            "name": "Cliente Test",
            "taxId": f"NIT-{uuid.uuid4().hex[:6]}",
            "notes": None,
            "nit": CLIENT_NIT,
            "nrc": CLIENT_NRC,
            "defaultTipoOperacion": "1",
            "defaultTipoIngreso": "3",
        }
        body.update(overrides)
        response = self.post("/api/clients", json=body)
        assert response.status_code == 201, response.text
        return response.json()["id"]

    def create_period(self, client_id: str, year: int = 2026, month: int = 1) -> str:
        response = self.post(f"/api/clients/{client_id}/periods", json={"year": year, "month": month})
        assert response.status_code == 201, response.text
        return response.json()["id"]

    def setup_period(self, **client_overrides: Any) -> tuple[str, str]:
        client_id = self.create_client(**client_overrides)
        return client_id, self.create_period(client_id)

    def upload(
        self,
        client_id: str,
        period_id: str,
        file_name: str = "factura.pdf",
        content: bytes | None = None,
        kind: str = "PDF",
    ) -> Response:
        content = fake_pdf(record()) if content is None else content
        mime = "application/pdf" if kind == "PDF" else "application/vnd.ms-excel"
        return self.post(
            f"/api/clients/{client_id}/periods/{period_id}/uploads",
            files={"file": (file_name, content, mime)},
            data={"sourceFileKind": kind},
        )

    def documents(self, client_id: str, period_id: str) -> list[dict[str, Any]]:
        response = self.get(f"/api/clients/{client_id}/periods/{period_id}/documents")
        assert response.status_code == 200, response.text
        return response.json()

    def create_run(self, client_id: str, period_id: str) -> Response:
        return self.post(f"/api/clients/{client_id}/periods/{period_id}/runs")


def run_extractions(session_factory: sessionmaker[Session], storage: FileStorage, settings: Settings) -> int:
    """Drain every Pending upload extraction synchronously. Returns how many were processed."""
    processed = 0
    with session_factory() as session:
        while (upload_id := try_claim_extraction(session)) is not None:
            process_extraction(session, storage, settings, upload_id)
            processed += 1
    return processed


def run_generations(session_factory: sessionmaker[Session], storage: FileStorage, settings: Settings) -> int:
    processed = 0
    with session_factory() as session:
        while (run_id := try_claim_run(session)) is not None:
            process_run(session, storage, settings, run_id)
            processed += 1
    return processed
