"""Render anexo rows to CSV bytes, driven only by an AnexoSpec."""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.anexos.normalize import money, sanitize_text, with_prefix
from app.anexos.spec import AnexoSpec, ColumnFormat, ColumnKind, ColumnSpec
from app.domain import Issue, IssueSeverity


@dataclass
class RenderRow:
    values: Mapping[str, Any]
    label: str  # used to prefix issues ("Documento <label>: ...")


@dataclass
class RenderedCsv:
    content: bytes
    issues: list[Issue] = field(default_factory=list)


def render_csv(spec: AnexoSpec, rows: Sequence[RenderRow]) -> RenderedCsv:
    file = spec.file
    lines: list[str] = []
    issues: list[Issue] = []
    for row in rows:
        cells: dict[str, str] = {}
        amounts: dict[str, Decimal] = {}
        for column in spec.columns:
            if column.kind is ColumnKind.SUM:
                total = sum((amounts[ref] for ref in column.sum_of), Decimal("0.00"))
                amounts[column.letter] = total
                cells[column.letter] = f"{total:.2f}"
                continue
            raw = column.value if column.kind is ColumnKind.CONSTANT else row.values.get(column.source or "")
            text, cell_issues, amount = _render_cell(column, raw, spec)
            if amount is not None:
                amounts[column.letter] = amount
            cells[column.letter] = text
            issues.extend(with_prefix(issue, row.label) for issue in cell_issues)
        lines.append(file.delimiter.join(cells[c.letter] for c in spec.columns))
    body = "".join(line + file.line_ending for line in lines)
    return RenderedCsv(content=body.encode(file.encoding), issues=_dedupe(issues))


def _render_cell(column: ColumnSpec, raw: Any, spec: AnexoSpec) -> tuple[str, list[Issue], Decimal | None]:
    if column.format is ColumnFormat.MONEY:
        amount = money(raw)
        if amount < 0:
            raise ValueError(f"columna {column.letter}: monto negativo {amount}")
        return f"{amount:.2f}", [], amount

    if column.format is ColumnFormat.DATE:
        if not isinstance(raw, dt.date):
            raise ValueError(f"columna {column.letter}: se esperaba una fecha, se recibió {raw!r}")
        return raw.strftime("%d/%m/%Y"), [], None

    field_name = column.source or column.letter
    text, issues = sanitize_text(
        "" if raw is None else str(raw),
        field_name=field_name,
        encoding=spec.file.encoding,
        delimiter=spec.file.delimiter,
    )
    if column.strip_dashes:
        text = text.replace("-", "")
    if column.width is not None and text:
        if len(text) > column.width:
            issues.append(
                Issue(
                    code="value_exceeds_width",
                    severity=IssueSeverity.ERROR,
                    message=(
                        f"el valor {text!r} de la columna {column.letter} ({column.name}) excede "
                        f"{column.width} caracteres."
                    ),
                    field=field_name,
                )
            )
        else:
            text = text.rjust(column.width, column.pad_char)
    return text, issues, None


def _dedupe(issues: list[Issue]) -> list[Issue]:
    return list(dict.fromkeys(issues))
