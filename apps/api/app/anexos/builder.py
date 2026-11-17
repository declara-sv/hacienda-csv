"""Build the F-07 sales anexos (Anexo 1 contribuyentes, Anexo 2 consumidor final) for a period."""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from decimal import Decimal

from app.anexos.normalize import document_label, money, normalize_receptor, with_prefix
from app.anexos.rules import anexo_for_tipo, check_period, renta_output_codes
from app.anexos.spec import default_registry
from app.anexos.validation import validate_for_anexo
from app.anexos.writer import RenderRow, render_csv
from app.domain import (
    AnexoBuildResult,
    ClientProfile,
    GeneratedCsv,
    Issue,
    IssueSeverity,
    ReviewedDocument,
    TipoDte,
)


def _sort_key(document: ReviewedDocument) -> tuple[dt.date, bool, dt.time, str]:
    record = document.record
    return (
        record.fecha_emision or dt.date.min,
        record.hora_emision is None,
        record.hora_emision or dt.time.min,
        record.codigo_generacion or "",
    )


def build_sales_anexos(
    *, year: int, month: int, client: ClientProfile, documents: list[ReviewedDocument]
) -> AnexoBuildResult:
    """Render one CSV per non-empty sales anexo.

    Every document is checked with ``validate_for_anexo`` plus a period guard; if any Error is
    found no file is produced and the result carries the issues. Documents of other tipos are
    skipped with a Warning.
    """
    check_period(year, month)
    issues: list[Issue] = []
    buckets: dict[int, list[ReviewedDocument]] = {1: [], 2: []}

    for document in documents:
        record = document.record
        label = document_label(document)
        anexo = anexo_for_tipo(record.tipo_dte)
        if anexo is None:
            issues.append(
                Issue(
                    code="tipo_not_in_sales_anexo",
                    severity=IssueSeverity.WARNING,
                    message=(
                        f"Documento {label}: el tipo de DTE {record.tipo_dte!r} no se reporta en los anexos "
                        "de ventas; se omitió."
                    ),
                    field="tipo_dte",
                )
            )
            continue
        doc_issues = validate_for_anexo(document, year=year, month=month, client=client)
        fecha = record.fecha_emision
        if fecha is not None and (fecha.year, fecha.month) != (year, month):
            doc_issues.append(
                Issue(
                    code="outside_period",
                    severity=IssueSeverity.ERROR,
                    message=(
                        f"la fecha de emisión {fecha:%d/%m/%Y} no pertenece al período {month:02d}/{year}."
                    ),
                    field="fecha_emision",
                )
            )
        issues.extend(with_prefix(issue, label) for issue in doc_issues)
        buckets[anexo].append(document)

    if _has_errors(issues):
        return AnexoBuildResult(files=[], issues=_dedupe(issues))

    registry = default_registry()
    files: list[GeneratedCsv] = []
    for anexo, docs in buckets.items():
        if not docs:
            continue
        spec = registry.for_period(anexo, year, month)
        if spec is None:  # validate_for_anexo already reported it; keep the type checker honest
            continue
        rows = (
            _anexo1_rows(docs, client, year=year, month=month)
            if anexo == 1
            else _anexo2_rows(docs, client, year=year, month=month)
        )
        rendered = render_csv(spec, rows)
        issues.extend(rendered.issues)
        files.append(
            GeneratedCsv(
                anexo=anexo,
                file_name=spec.file_name(year, month),
                content=rendered.content,
                row_count=len(rows),
            )
        )

    if _has_errors(issues):
        files = []
    return AnexoBuildResult(files=files, issues=_dedupe(issues))


def _anexo1_rows(
    documents: list[ReviewedDocument], client: ClientProfile, *, year: int, month: int
) -> list[RenderRow]:
    rows: list[RenderRow] = []
    for document in sorted(documents, key=_sort_key):
        record = document.record
        receptor = normalize_receptor(record.receptor_nit, record.receptor_dui, record.receptor_nrc)
        operacion, ingreso = renta_output_codes(document, client, year=year, month=month)
        rows.append(
            RenderRow(
                label=document_label(document),
                values={
                    "fecha_emision": record.fecha_emision,
                    "tipo_dte": record.tipo_dte.strip(),
                    "numero_control": record.numero_control,
                    "sello_recepcion": record.sello_recepcion,
                    "codigo_generacion": record.codigo_generacion,
                    "receptor_nit_nrc": receptor.nit_nrc,
                    "receptor_dui": receptor.dui,
                    "receptor_nombre": record.receptor_nombre,
                    "total_exentas": record.total_exentas,
                    "total_no_sujetas": record.total_no_sujetas,
                    "total_gravadas": record.total_gravadas,
                    "iva": record.iva,
                    "tipo_operacion_renta": operacion,
                    "tipo_ingreso_renta": ingreso,
                },
            )
        )
    return rows


def _anexo2_rows(
    documents: list[ReviewedDocument], client: ClientProfile, *, year: int, month: int
) -> list[RenderRow]:
    groups: dict[tuple[dt.date, str, str], list[ReviewedDocument]] = {}
    for document in documents:
        operacion, ingreso = renta_output_codes(document, client, year=year, month=month)
        fecha = document.record.fecha_emision or dt.date.min
        groups.setdefault((fecha, operacion, ingreso), []).append(document)

    ordered = sorted(
        ((key, sorted(docs, key=_sort_key)) for key, docs in groups.items()),
        key=lambda item: _sort_key(item[1][0]),
    )
    rows: list[RenderRow] = []
    for (fecha, operacion, ingreso), docs in ordered:
        records = [d.record for d in docs]
        rows.append(
            RenderRow(
                label=f"del {fecha:%d/%m/%Y}",
                values={
                    "fecha_emision": fecha,
                    "tipo_dte": TipoDte.FACTURA.value,
                    "codigo_generacion_del": records[0].codigo_generacion,
                    "codigo_generacion_al": records[-1].codigo_generacion,
                    "total_exentas": _sum(r.total_exentas for r in records),
                    "total_no_sujetas": _sum(r.total_no_sujetas for r in records),
                    "total_gravadas": _sum(r.total_gravadas for r in records),
                    "tipo_operacion_renta": operacion,
                    "tipo_ingreso_renta": ingreso,
                },
            )
        )
    return rows


def _sum(values: Iterable[Decimal]) -> Decimal:
    return sum((money(v) for v in values), Decimal("0.00"))


def _has_errors(issues: list[Issue]) -> bool:
    return any(issue.severity is IssueSeverity.ERROR for issue in issues)


def _dedupe(issues: list[Issue]) -> list[Issue]:
    return list(dict.fromkeys(issues))
