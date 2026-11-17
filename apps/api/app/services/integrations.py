"""Adapter over `app.extraction` and `app.anexos`.

Those packages are imported lazily so the API starts even when they are incomplete. Every caller
goes through the module attributes here (`integrations.validate_record(...)`), which lets tests
replace them with fakes via monkeypatch.
"""

from __future__ import annotations

import importlib
import logging
from collections import defaultdict
from types import ModuleType
from typing import Any

from app.config import Settings
from app.domain import (
    AnexoBuildResult,
    ClientProfile,
    DteRecord,
    ExtractionResult,
    Issue,
    IssueSeverity,
    ReviewedDocument,
)

logger = logging.getLogger(__name__)

_FALLBACK_ANEXO_BY_TIPO = {"01": 2, "03": 1, "05": 1, "06": 1}


def _module(name: str) -> ModuleType | None:
    try:
        return importlib.import_module(name)
    except Exception:  # an in-progress module must not take the API down
        logger.warning("No se pudo importar %s.", name, exc_info=True)
        return None


def _function(module_name: str, attr: str) -> Any | None:
    module = _module(module_name)
    return getattr(module, attr, None) if module is not None else None


# --- Extraction ---------------------------------------------------------------------------------


def extract_pdf(pdf_bytes: bytes, settings: Settings) -> ExtractionResult:
    extract = _function("app.extraction", "extract_pdf")
    if extract is None:
        raise RuntimeError("La lectura de PDF aún no está disponible.")
    build_ai = _function("app.extraction", "build_ai_extractor")
    ai = build_ai(settings) if build_ai is not None else None
    return extract(pdf_bytes, ai=ai)


def validate_record(record: DteRecord) -> list[Issue]:
    fn = _function("app.extraction", "validate_record")
    return list(fn(record)) if fn is not None else []


def validate_in_period(record: DteRecord, *, year: int, month: int, client: ClientProfile) -> list[Issue]:
    fn = _function("app.extraction", "validate_in_period")
    return list(fn(record, year=year, month=month, client=client)) if fn is not None else []


def find_duplicate_codes(items: list[tuple[str, str | None]]) -> dict[str, list[Issue]]:
    fn = _function("app.extraction", "find_duplicate_codes")
    if fn is not None:
        return dict(fn(items))

    by_code: dict[str, list[str]] = defaultdict(list)
    for doc_id, code in items:
        if code:
            by_code[code.strip().upper()].append(doc_id)
    result: dict[str, list[Issue]] = {}
    for ids in by_code.values():
        if len(ids) > 1:
            issue = Issue(
                code="DUPLICATE_CODIGO_GENERACION",
                severity=IssueSeverity.ERROR,
                message="El código de generación está repetido en el período.",
                field="codigoGeneracion",
            )
            for doc_id in ids:
                result[doc_id] = [issue]
    return result


# --- Anexos -------------------------------------------------------------------------------------


def validate_for_anexo(
    document: ReviewedDocument, *, year: int, month: int, client: ClientProfile
) -> list[Issue]:
    fn = _function("app.anexos", "validate_for_anexo")
    return list(fn(document, year=year, month=month, client=client)) if fn is not None else []


def anexo_for_tipo(tipo_dte: str) -> int | None:
    fn = _function("app.anexos", "anexo_for_tipo")
    if fn is not None:
        return fn(tipo_dte)
    return _FALLBACK_ANEXO_BY_TIPO.get(tipo_dte)


def renta_catalog() -> dict | None:
    """`{"tipoOperacion": [{"code","label"}], "tipoIngreso": [...]}` or None when unavailable."""
    module = _module("app.anexos")
    catalog = getattr(module, "RENTA_CATALOG", None) if module is not None else None
    return catalog if isinstance(catalog, dict) else None


def build_sales_anexos(
    *, year: int, month: int, client: ClientProfile, documents: list[ReviewedDocument]
) -> AnexoBuildResult:
    fn = _function("app.anexos", "build_sales_anexos")
    if fn is None:
        raise RuntimeError("El generador de anexos aún no está disponible.")
    return fn(year=year, month=month, client=client, documents=documents)
