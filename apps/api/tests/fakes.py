"""Deterministic stand-ins for app.extraction / app.anexos so API tests don't depend on them."""

from __future__ import annotations

import json
from collections import defaultdict

import pytest

from app.domain import (
    AnexoBuildResult,
    ClientProfile,
    DteRecord,
    ExtractionResult,
    GeneratedCsv,
    Issue,
    IssueSeverity,
    ReviewedDocument,
)
from app.services import integrations

ANEXO_BY_TIPO = {"01": 2, "03": 1, "05": 1, "06": 1}
RENTA_CATALOG = {
    "tipoOperacion": [{"code": "1", "label": "Gravada"}, {"code": "2", "label": "No gravada"}],
    "tipoIngreso": [{"code": "3", "label": "Comercial"}, {"code": "4", "label": "Servicios"}],
}


def _error(code: str, message: str, field: str | None = None) -> Issue:
    return Issue(code=code, severity=IssueSeverity.ERROR, message=message, field=field)


def extract_pdf(pdf_bytes: bytes, settings) -> ExtractionResult:
    try:
        payload = json.loads(pdf_bytes)
    except ValueError as exc:
        raise ValueError("PDF ilegible") from exc
    return ExtractionResult.model_validate(payload)


def validate_record(record: DteRecord) -> list[Issue]:
    if not record.codigo_generacion:
        return [_error("CODIGO_REQUIRED", "Falta el código de generación.", "codigoGeneracion")]
    return []


def validate_in_period(record: DteRecord, *, year: int, month: int, client: ClientProfile) -> list[Issue]:
    issues = []
    fecha = record.fecha_emision
    if fecha is not None and (fecha.year, fecha.month) != (year, month):
        issues.append(_error("OUT_OF_PERIOD", "La fecha está fuera del período.", "fechaEmision"))
    if client.nit and record.emisor_nit != client.nit:
        issues.append(_error("NOT_CLIENT_SALE", "El emisor no es el cliente.", "emisorNit"))
    return issues


def find_duplicate_codes(items: list[tuple[str, str | None]]) -> dict[str, list[Issue]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for doc_id, code in items:
        if code:
            groups[code].append(doc_id)
    issue = _error("DUPLICATE", "Código de generación repetido.", "codigoGeneracion")
    return {doc_id: [issue] for ids in groups.values() if len(ids) > 1 for doc_id in ids}


def validate_for_anexo(
    document: ReviewedDocument, *, year: int, month: int, client: ClientProfile
) -> list[Issue]:
    if document.record.tipo_dte not in ANEXO_BY_TIPO:
        return [Issue(code="NOT_EXPORTED", severity=IssueSeverity.WARNING, message="No va a anexos.")]
    if not document.tipo_operacion_renta or not document.tipo_ingreso_renta:
        return [_error("RENTA_REQUIRED", "Faltan los códigos de Renta.", "tipoOperacionRenta")]
    return []


def anexo_for_tipo(tipo_dte: str) -> int | None:
    return ANEXO_BY_TIPO.get(tipo_dte)


def renta_catalog() -> dict:
    return RENTA_CATALOG


def build_sales_anexos(
    *, year: int, month: int, client: ClientProfile, documents: list[ReviewedDocument]
) -> AnexoBuildResult:
    anexo2_days: dict[str, list[ReviewedDocument]] = defaultdict(list)
    anexo1: list[ReviewedDocument] = []
    for doc in documents:
        anexo = ANEXO_BY_TIPO.get(doc.record.tipo_dte)
        if anexo == 2:
            anexo2_days[str(doc.record.fecha_emision)].append(doc)
        elif anexo == 1:
            anexo1.append(doc)

    files = []
    period = f"{year:04d}{month:02d}"
    if anexo1:
        lines = [f"{d.record.fecha_emision};{d.record.numero_control};{d.record.total}" for d in anexo1]
        files.append(_csv(1, f"anexo1_{period}.csv", lines))
    if anexo2_days:
        lines = [
            f"{day};{len(docs)};{sum(d.record.total for d in docs)}"
            for day, docs in sorted(anexo2_days.items())
        ]
        files.append(_csv(2, f"anexo2_{period}.csv", lines))
    issues = [
        Issue(code="FAKE_NOTE", severity=IssueSeverity.WARNING, message="Generado con el builder falso.")
    ]
    return AnexoBuildResult(files=files, issues=issues)


def _csv(anexo: int, name: str, lines: list[str]) -> GeneratedCsv:
    content = "".join(f"{line}\r\n" for line in lines).encode("cp1252")
    return GeneratedCsv(anexo=anexo, file_name=name, content=content, row_count=len(lines))


def install(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "extract_pdf",
        "validate_record",
        "validate_in_period",
        "find_duplicate_codes",
        "validate_for_anexo",
        "anexo_for_tipo",
        "renta_catalog",
        "build_sales_anexos",
    ):
        monkeypatch.setattr(integrations, name, globals()[name])
