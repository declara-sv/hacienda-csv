"""Document-level validations shared by the parser, the AI fallback and the review table."""

from __future__ import annotations

import re
from collections import defaultdict
from decimal import Decimal

from app.domain import ClientProfile, DteRecord, Issue, IssueSeverity, TipoDte

TOLERANCE = Decimal("0.01")
IVA_RATE = Decimal("0.13")

CODIGO_GENERACION_RE = re.compile(
    r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$"
)
NUMERO_CONTROL_RE = re.compile(r"^DTE-(\d{2})-[A-Za-z0-9]{8}-\d{15}$")

KNOWN_TIPOS = {t.value for t in TipoDte}
IVA_TIPOS = {TipoDte.CCF.value, TipoDte.NOTA_CREDITO.value, TipoDte.NOTA_DEBITO.value}
SALES_ANEXO_TIPOS = {TipoDte.FACTURA.value} | IVA_TIPOS

AMOUNT_FIELDS = ("total_no_sujetas", "total_exentas", "total_gravadas", "iva", "iva_retenido", "total")

FIELD_LABELS = {
    "tipo_dte": "tipo de documento",
    "codigo_generacion": "código de generación",
    "numero_control": "número de control",
    "sello_recepcion": "sello de recepción",
    "fecha_emision": "fecha de emisión",
    "emisor_nit": "NIT del emisor",
    "total_no_sujetas": "ventas no sujetas",
    "total_exentas": "ventas exentas",
    "total_gravadas": "ventas gravadas",
    "iva": "IVA",
    "iva_retenido": "IVA retenido",
    "total": "total",
}


def _error(code: str, message: str, field: str | None = None) -> Issue:
    return Issue(code=code, severity=IssueSeverity.ERROR, message=message, field=field)


def _warning(code: str, message: str, field: str | None = None) -> Issue:
    return Issue(code=code, severity=IssueSeverity.WARNING, message=message, field=field)


def _missing(field: str) -> Issue:
    return _error("missing_required_field", f"Falta el {FIELD_LABELS[field]}.", field)


def _blank(value: str | None) -> bool:
    return value is None or not value.strip() or set(value.strip()) <= {"-"}


def _digits(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


def validate_record(record: DteRecord) -> list[Issue]:
    """Validations that depend only on the document itself."""
    issues: list[Issue] = []
    tipo = (record.tipo_dte or "").strip()

    if not tipo:
        issues.append(_missing("tipo_dte"))
    elif tipo not in KNOWN_TIPOS:
        issues.append(
            _error(
                "invalid_tipo_dte", f"El tipo de documento '{tipo}' no es un tipo de DTE válido.", "tipo_dte"
            )
        )

    if _blank(record.codigo_generacion):
        issues.append(_missing("codigo_generacion"))
    elif not CODIGO_GENERACION_RE.match((record.codigo_generacion or "").strip()):
        issues.append(
            _error(
                "invalid_codigo_generacion",
                f"El código de generación '{record.codigo_generacion}' no tiene el formato "
                "XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX.",
                "codigo_generacion",
            )
        )

    if _blank(record.numero_control):
        issues.append(_missing("numero_control"))
    else:
        match = NUMERO_CONTROL_RE.match((record.numero_control or "").strip())
        if not match:
            issues.append(
                _error(
                    "invalid_numero_control",
                    f"El número de control '{record.numero_control}' no tiene el formato "
                    "DTE-NN-XXXXXXXX-NNNNNNNNNNNNNNN.",
                    "numero_control",
                )
            )
        elif tipo and match.group(1) != tipo:
            issues.append(
                _error(
                    "numero_control_tipo_mismatch",
                    f"El número de control indica tipo {match.group(1)} pero el documento es tipo {tipo}.",
                    "numero_control",
                )
            )

    if _blank(record.sello_recepcion):
        make = _error if tipo in IVA_TIPOS else _warning
        issues.append(
            make("missing_sello_recepcion", "El documento no tiene sello de recepción.", "sello_recepcion")
        )

    if record.fecha_emision is None:
        issues.append(_missing("fecha_emision"))

    if _blank(record.emisor_nit):
        issues.append(_missing("emisor_nit"))

    if tipo in IVA_TIPOS and _blank(record.receptor_nit) and _blank(record.receptor_dui):
        issues.append(
            _error(
                "missing_receptor_id",
                "Falta el NIT (o DUI) del receptor, obligatorio para el anexo de ventas a contribuyentes.",
                "receptor_nit",
            )
        )

    for name in AMOUNT_FIELDS:
        if getattr(record, name) < 0:
            issues.append(
                _error("negative_amount", f"El monto de {FIELD_LABELS[name]} no puede ser negativo.", name)
            )

    computed = record.total_no_sujetas + record.total_exentas + record.total_gravadas + record.iva
    if abs(computed - record.total) > TOLERANCE:
        issues.append(
            _error(
                "amounts_do_not_reconcile",
                f"No sujetas + exentas + gravadas + IVA = {computed:.2f}, pero el total es "
                f"{record.total:.2f}.",
                "total",
            )
        )

    if tipo == TipoDte.FACTURA.value and record.iva != 0:
        issues.append(
            _error(
                "factura_iva_not_zero",
                "En una factura el IVA va incluido en las ventas gravadas; el IVA debe ser 0.00.",
                "iva",
            )
        )

    if tipo in IVA_TIPOS:
        expected = (record.total_gravadas * IVA_RATE).quantize(Decimal("0.01"))
        if abs(expected - record.iva) > TOLERANCE:
            issues.append(
                _warning(
                    "iva_mismatch",
                    f"El IVA ({record.iva:.2f}) no corresponde al 13% de las ventas gravadas "
                    f"({expected:.2f}).",
                    "iva",
                )
            )

    return issues


def validate_in_period(record: DteRecord, *, year: int, month: int, client: ClientProfile) -> list[Issue]:
    """Validations that depend on the period being declared and on the client."""
    issues: list[Issue] = []

    fecha = record.fecha_emision
    if fecha is not None and (fecha.year != year or fecha.month != month):
        issues.append(
            _error(
                "outside_period",
                f"La fecha de emisión {fecha.isoformat()} está fuera del período {month:02d}/{year}.",
                "fecha_emision",
            )
        )

    mismatched: list[str] = []
    if (
        _digits(client.nit)
        and _digits(record.emisor_nit)
        and _digits(client.nit) != _digits(record.emisor_nit)
    ):
        mismatched.append(f"NIT {record.emisor_nit}")
    if (
        _digits(client.nrc)
        and _digits(record.emisor_nrc)
        and _digits(client.nrc) != _digits(record.emisor_nrc)
    ):
        mismatched.append(f"NRC {record.emisor_nrc}")
    if mismatched:
        issues.append(
            _error(
                "not_client_sale",
                f"El emisor ({', '.join(mismatched)}) no coincide con el cliente: "
                "no es una venta del cliente.",
                "emisor_nit" if mismatched[0].startswith("NIT") else "emisor_nrc",
            )
        )

    tipo = (record.tipo_dte or "").strip()
    if tipo and tipo not in SALES_ANEXO_TIPOS:
        issues.append(
            _warning(
                "not_exported_to_sales_anexos",
                f"Los documentos tipo {tipo} no se incluyen en los anexos de ventas.",
                "tipo_dte",
            )
        )
    return issues


def find_duplicate_codes(items: list[tuple[str, str | None]]) -> dict[str, list[Issue]]:
    """Flag every document whose código de generación (case-insensitive) appears in another document.

    Returns an entry for every doc_id in `items`; documents without duplicates get an empty list.
    """
    by_code: dict[str, set[str]] = defaultdict(set)
    printed: dict[str, str] = {}
    result: dict[str, list[Issue]] = {}
    for doc_id, codigo in items:
        result.setdefault(doc_id, [])
        if _blank(codigo):
            continue
        assert codigo is not None
        key = codigo.strip().lower()
        by_code[key].add(doc_id)
        printed.setdefault(key, codigo.strip())

    for key, doc_ids in by_code.items():
        if len(doc_ids) < 2:
            continue
        for doc_id in doc_ids:
            result[doc_id].append(
                _error(
                    "duplicate_codigo_generacion",
                    f"El código de generación {printed[key]} aparece en {len(doc_ids)} documentos del "
                    "período; excluya las copias.",
                    "codigo_generacion",
                )
            )
    return result
