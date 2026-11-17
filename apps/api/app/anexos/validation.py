"""Anexo-specific checks for one reviewed document.

Covers what the anexo needs to render a valid row (Renta codes, receptor identification, fields
that land in a column, amounts). Document-level checks (identifier formats, totals, period,
emisor, duplicates) live in ``app.extraction``.
"""

from __future__ import annotations

from decimal import Decimal

from app.anexos.catalog import TIPO_INGRESO_CODES, TIPO_OPERACION_CODES, renta_required
from app.anexos.normalize import money, normalize_receptor, sanitize_text
from app.anexos.rules import anexo_for_tipo, check_period, effective_renta_codes
from app.anexos.spec import AnexoSpec, default_registry
from app.domain import ClientProfile, DteRecord, Issue, IssueSeverity, ReviewedDocument

IVA_RATE = Decimal("0.13")
IVA_TOLERANCE = Decimal("0.01")

_AMOUNT_FIELDS = ("total_no_sujetas", "total_exentas", "total_gravadas", "iva")
_TEXT_FIELDS = {
    1: ("numero_control", "sello_recepcion", "codigo_generacion", "receptor_nombre"),
    2: ("codigo_generacion",),
}
_REQUIRED_TEXT = {
    1: (
        ("codigo_generacion", "el código de generación"),
        ("numero_control", "el número de control"),
        ("sello_recepcion", "el sello de recepción"),
        ("receptor_nombre", "el nombre del receptor"),
    ),
    2: (("codigo_generacion", "el código de generación"),),
}


def _error(code: str, message: str, field: str | None = None) -> Issue:
    return Issue(code=code, severity=IssueSeverity.ERROR, message=message, field=field)


def _warning(code: str, message: str, field: str | None = None) -> Issue:
    return Issue(code=code, severity=IssueSeverity.WARNING, message=message, field=field)


def validate_for_anexo(
    document: ReviewedDocument, *, year: int, month: int, client: ClientProfile
) -> list[Issue]:
    """Issues that block (Error) or qualify (Warning) this document's row in its sales anexo.

    Documents whose tipo is not reported in a sales anexo return no issues here; the builder
    skips them with a Warning and extraction already flags them.
    """
    check_period(year, month)
    record = document.record
    anexo = anexo_for_tipo(record.tipo_dte)
    if anexo is None:
        return []

    issues: list[Issue] = []
    spec = default_registry().for_period(anexo, year, month)
    if spec is None:
        issues.append(
            _error(
                "anexo_spec_not_found",
                f"no hay especificación del Anexo {anexo} para el período {month:02d}/{year}.",
            )
        )

    if record.fecha_emision is None:
        issues.append(_error("missing_fecha_emision", "falta la fecha de emisión.", "fecha_emision"))

    for field_name, label in _REQUIRED_TEXT[anexo]:
        if not (getattr(record, field_name) or "").strip():
            issues.append(
                _error(f"missing_{field_name}", f"falta {label} (requerido en el Anexo {anexo}).", field_name)
            )

    for field_name in _AMOUNT_FIELDS:
        if getattr(record, field_name) < 0:
            issues.append(
                _error("negative_amount", "los montos del anexo no pueden ser negativos.", field_name)
            )

    issues.extend(_renta_issues(document, client, year=year, month=month))

    if anexo == 1:
        issues.extend(
            normalize_receptor(record.receptor_nit, record.receptor_dui, record.receptor_nrc).issues
        )
        issues.extend(_debito_fiscal_issues(record))
    else:
        if record.hora_emision is None:
            issues.append(
                _warning(
                    "missing_hora_emision",
                    "falta la hora de emisión; dentro del día se ordena después de los que sí la tienen.",
                    "hora_emision",
                )
            )
        if money(record.iva) != 0:
            issues.append(
                _warning(
                    "factura_with_iva",
                    "una factura (01) no debería separar el IVA; el Anexo 2 solo suma las ventas "
                    "gravadas (IVA incluido).",
                    "iva",
                )
            )

    if spec is not None:
        issues.extend(_text_issues(record, anexo, spec))
    return issues


def _renta_issues(document: ReviewedDocument, client: ClientProfile, *, year: int, month: int) -> list[Issue]:
    if not renta_required(year, month):
        return []
    operacion, ingreso = effective_renta_codes(document, client)
    issues: list[Issue] = []
    checks = (
        ("tipo_operacion_renta", "tipo de operación", operacion, TIPO_OPERACION_CODES),
        ("tipo_ingreso_renta", "tipo de ingreso", ingreso, TIPO_INGRESO_CODES),
    )
    for field_name, label, code, catalog in checks:
        if code is None:
            issues.append(
                _error(
                    f"missing_{field_name}",
                    f"falta el {label} de Renta (obligatorio desde 01/2025); defínalo en el documento "
                    "o como valor por defecto del cliente.",
                    field_name,
                )
            )
        elif code not in catalog:
            issues.append(
                _error(
                    f"unknown_{field_name}",
                    f"el {label} de Renta {code!r} no existe en el catálogo.",
                    field_name,
                )
            )
    return issues


def _debito_fiscal_issues(record: DteRecord) -> list[Issue]:
    expected = money(money(record.total_gravadas) * IVA_RATE)
    actual = money(record.iva)
    if abs(actual - expected) > IVA_TOLERANCE:
        return [
            _warning(
                "iva_mismatch",
                f"el débito fiscal {actual} no coincide con el 13% de las ventas gravadas ({expected}).",
                "iva",
            )
        ]
    return []


def _text_issues(record: DteRecord, anexo: int, spec: AnexoSpec) -> list[Issue]:
    issues: list[Issue] = []
    for field_name in _TEXT_FIELDS[anexo]:
        value = getattr(record, field_name)
        if value:
            _, found = sanitize_text(
                value, field_name=field_name, encoding=spec.file.encoding, delimiter=spec.file.delimiter
            )
            issues.extend(found)
    return issues
