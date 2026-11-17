"""Deterministic parser for DTE PDFs rendered by the Ministerio de Hacienda template.

The MH "sistema de facturación" renders every DTE with JasperReports: a centered
`DOCUMENTO TRIBUTARIO ELECTRÓNICO` header, the document title, the identification block
(código de generación, número de control, sello, fecha y hora), then EMISOR and RECEPTOR side by
side, the item table and a totals block on the right. Labels are right-aligned and values start at a
fixed x position, so the parties are read per column using word coordinates.

Only Factura (01) samples have been seen. CCF / NC / ND are read by label as best effort; anything
missing is reported as an Error so that the caller falls back to AI instead of trusting zeros.
"""

from __future__ import annotations

import datetime as dt
import re
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from app.domain import DteRecord, Issue, IssueSeverity, TipoDte

from .layout import Line, Page, Word, label_pattern, normalize

HEADER_TITLE = "DOCUMENTO TRIBUTARIO ELECTRONICO"

TITLE_TO_TIPO: dict[str, str] = {
    "FACTURA": TipoDte.FACTURA,
    "FACTURA ELECTRONICA": TipoDte.FACTURA,
    "FACTURA CONSUMIDOR FINAL": TipoDte.FACTURA,
    "COMPROBANTE DE CREDITO FISCAL": TipoDte.CCF,
    "NOTA DE REMISION": TipoDte.NOTA_REMISION,
    "NOTA DE CREDITO": TipoDte.NOTA_CREDITO,
    "NOTA DE DEBITO": TipoDte.NOTA_DEBITO,
    "COMPROBANTE DE RETENCION": TipoDte.COMPROBANTE_RETENCION,
    "COMPROBANTE DE LIQUIDACION": TipoDte.COMPROBANTE_LIQUIDACION,
    "DOCUMENTO CONTABLE DE LIQUIDACION": TipoDte.DOCUMENTO_CONTABLE_LIQUIDACION,
    "FACTURA DE EXPORTACION": TipoDte.FACTURA_EXPORTACION,
    "FACTURA DE SUJETO EXCLUIDO": TipoDte.FACTURA_SUJETO_EXCLUIDO,
    "FACTURA SUJETO EXCLUIDO": TipoDte.FACTURA_SUJETO_EXCLUIDO,
    "COMPROBANTE DE DONACION": TipoDte.COMPROBANTE_DONACION,
}

IVA_TIPOS = {TipoDte.CCF.value, TipoDte.NOTA_CREDITO.value, TipoDte.NOTA_DEBITO.value}

_AMOUNT = r"(-?\$?\s?(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2})(?!\d)"
_FLAGS = re.IGNORECASE


def _header_re(label: str) -> re.Pattern[str]:
    return re.compile(label_pattern(label) + r"\s*:\s*(\S+)", _FLAGS)


_CODIGO_RE = _header_re("Código de Generación")
_CONTROL_RE = _header_re("Número de Control")
_SELLO_RE = _header_re("Sello de Recepción")
_FECHA_RE = re.compile(
    r"(?:" + label_pattern("Fecha y Hora de Generación") + "|" + label_pattern("Fecha de Emisión") + r")"
    r"\s*:\s*(\S+)(?:\s+(\d{1,2}:\d{2}(?::\d{2})?))?",
    _FLAGS,
)
_CONTROL_TIPO_RE = re.compile(r"^DTE-(\d{2})-", _FLAGS)

_SUMA_VENTAS_RE = re.compile(label_pattern("Suma de Ventas") + r"\s*:?(.*)$", _FLAGS)
_DESCUENTO_RE = re.compile(
    r"(?:Descuento|Desc\.).*?ventas\s+(no\s+sujetas|exentas|gravadas)\s*:?\s*" + _AMOUNT, _FLAGS
)
_IVA_RE = re.compile(
    r"(?:" + label_pattern("Impuesto al Valor Agregado") + r"|\bIVA)\s*\(?\s*13\s*%\s*\)?\s*:?\s*" + _AMOUNT,
    _FLAGS,
)
_IVA_RETENIDO_RE = re.compile(r"\bIVA\s+Retenido\s*:?\s*" + _AMOUNT, _FLAGS)
_TOTAL_RE = re.compile(label_pattern("Monto Total de la Operación") + r"\s*:?\s*" + _AMOUNT, _FLAGS)
_AMOUNT_RE = re.compile(_AMOUNT)

# Tokens that start the right-hand label on the identification lines; seeing one as a "value" means
# the left value was empty.
_RIGHT_LABEL_STARTS = {"MODELO", "TIPO", "FECHA", "VERSION"}

# Full-width headings that end the EMISOR / RECEPTOR block.
_PARTY_BLOCK_END = (
    "VENTA POR CUENTA DE TERCEROS",
    "DOCUMENTOS RELACIONADOS",
    "OTROS DOCUMENTOS ASOCIADOS",
    "CUERPO DEL DOCUMENTO",
)


@dataclass
class ParsedDocument:
    record: DteRecord
    issues: list[Issue] = field(default_factory=list)


@dataclass
class ParseOutcome:
    """Result of running the parser over a whole PDF.

    `failure` is set (and `documents` empty) when the PDF is not something the parser can read:
    no text at all, or not the MH template.
    """

    documents: list[ParsedDocument]
    raw_text: str
    failure: str | None = None
    failure_code: str | None = None


@dataclass
class _Segment:
    codigo: str | None
    pages: list[tuple[Page, list[Line]]]


# --------------------------------------------------------------------------------------------- public


def parse_pages(pages: list[Page]) -> ParseOutcome:
    page_lines = [(page, page.lines()) for page in pages]
    raw_text = "\n\n".join("\n".join(line.text for line in lines) for _, lines in page_lines)

    if not any(page.words for page in pages):
        return ParseOutcome(
            [],
            raw_text,
            failure="el PDF no contiene texto (puede ser un documento escaneado)",
            failure_code="pdf_has_no_text",
        )

    segments = _split_documents(page_lines)
    if not segments:
        return ParseOutcome(
            [],
            raw_text,
            failure="el formato del PDF no corresponde a la plantilla de DTE del Ministerio de Hacienda",
            failure_code="template_not_recognized",
        )

    return ParseOutcome([_parse_segment(segment) for segment in segments], raw_text)


# ----------------------------------------------------------------------------------------- segmenting


def _header_index(lines: list[Line]) -> int | None:
    for i, line in enumerate(lines):
        if HEADER_TITLE in normalize(line.text):
            return i
    return None


def _first_match(lines: list[Line], pattern: re.Pattern[str]) -> re.Match[str] | None:
    for line in lines:
        match = pattern.search(line.text)
        if match:
            return match
    return None


def _split_documents(page_lines: list[tuple[Page, list[Line]]]) -> list[_Segment]:
    """One segment per DTE. A page repeating the header with a new código de generación starts a new
    DTE; a page with the same código (repeated page header) or without header continues the current."""
    segments: list[_Segment] = []
    for page, lines in page_lines:
        header = _header_index(lines)
        if header is None:
            if segments:
                segments[-1].pages.append((page, lines))
            continue
        match = _first_match(lines[header:], _CODIGO_RE)
        codigo = _clean_value(match.group(1)) if match else None
        current = segments[-1] if segments else None
        if current is not None and (codigo is None or _same_code(current.codigo, codigo)):
            current.pages.append((page, lines))
        else:
            segments.append(_Segment(codigo=codigo, pages=[(page, lines)]))
    return segments


def _same_code(a: str | None, b: str | None) -> bool:
    return a is not None and b is not None and a.strip().lower() == b.strip().lower()


# ------------------------------------------------------------------------------------------- parsing


def _parse_segment(segment: _Segment) -> ParsedDocument:
    first_page, first_lines = segment.pages[0]
    all_lines = [line for _, lines in segment.pages for line in lines]
    issues: list[Issue] = []

    header = _header_index(first_lines) or 0
    head_lines = first_lines[header:]

    tipo, tipo_issues = _detect_tipo(head_lines)
    issues.extend(tipo_issues)

    fecha, hora = _parse_fecha(head_lines, issues)

    data: dict[str, object] = {
        "tipo_dte": tipo or "",
        "codigo_generacion": _value(head_lines, _CODIGO_RE),
        "numero_control": _value(head_lines, _CONTROL_RE),
        "sello_recepcion": _value(head_lines, _SELLO_RE),
        "fecha_emision": fecha,
        "hora_emision": hora,
    }
    data.update(_parse_parties(first_page, first_lines))
    data.update(_parse_amounts(all_lines, tipo, issues))

    return ParsedDocument(record=DteRecord.model_validate(data), issues=issues)


def _clean_value(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value or set(value) <= {"-"}:
        return None
    if value.endswith(":") or normalize(value) in _RIGHT_LABEL_STARTS:
        return None
    return value


def _value(lines: list[Line], pattern: re.Pattern[str]) -> str | None:
    match = _first_match(lines, pattern)
    return _clean_value(match.group(1)) if match else None


def _detect_tipo(head_lines: list[Line]) -> tuple[str | None, list[Issue]]:
    issues: list[Issue] = []

    title_parts: list[str] = []
    for line in head_lines[1:]:
        if _CODIGO_RE.search(line.text) or _CONTROL_RE.search(line.text):
            break
        title_parts.append(line.text)
        if len(title_parts) >= 3:
            break
    title = normalize(" ".join(title_parts))
    title = re.sub(r"\s+ELECTRONIC[AO]$", "", title)
    from_title = TITLE_TO_TIPO.get(title)
    if from_title is None:
        # Longest known title contained in the text (e.g. a version tag on the same line).
        for known in sorted(TITLE_TO_TIPO, key=len, reverse=True):
            if re.search(rf"\b{re.escape(known)}\b", title):
                from_title = TITLE_TO_TIPO[known]
                break

    control = _value(head_lines, _CONTROL_RE)
    control_match = _CONTROL_TIPO_RE.match(control) if control else None
    from_control = control_match.group(1) if control_match else None

    if from_title and from_control and str(from_title) != from_control:
        issues.append(
            Issue(
                code="tipo_dte_mismatch",
                severity=IssueSeverity.ERROR,
                message=(
                    f"El título del documento indica tipo {from_title} pero el número de control "
                    f"indica tipo {from_control}."
                ),
                field="tipo_dte",
            )
        )
    tipo = str(from_title) if from_title else from_control
    if tipo is None:
        issues.append(
            Issue(
                code="tipo_dte_not_detected",
                severity=IssueSeverity.ERROR,
                message="No se pudo determinar el tipo de documento.",
                field="tipo_dte",
            )
        )
    return tipo, issues


def _parse_fecha(head_lines: list[Line], issues: list[Issue]) -> tuple[dt.date | None, dt.time | None]:
    match = _first_match(head_lines, _FECHA_RE)
    if not match:
        return None, None
    raw_date, raw_time = match.group(1), match.group(2)
    fecha = parse_date(raw_date)
    if fecha is None and _clean_value(raw_date) is not None:
        issues.append(
            Issue(
                code="invalid_fecha_emision",
                severity=IssueSeverity.ERROR,
                message=f"La fecha de emisión '{raw_date}' no tiene un formato reconocido.",
                field="fecha_emision",
            )
        )
    return fecha, parse_time(raw_time) if raw_time else None


def parse_date(value: str | None) -> dt.date | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return dt.datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return None


def parse_time(value: str | None) -> dt.time | None:
    if not value:
        return None
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return dt.datetime.strptime(value.strip(), fmt).time()
        except ValueError:
            continue
    return None


def parse_amount(value: str | None) -> Decimal | None:
    if value is None:
        return None
    cleaned = value.replace("$", "").replace(",", "").replace(" ", "").strip()
    if not cleaned:
        return None
    try:
        return Decimal(cleaned).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


# ------------------------------------------------------------------------------------------- parties


def _party_block(page: Page, lines: list[Line]) -> tuple[float, float] | None:
    """Vertical range (top, bottom) of the EMISOR / RECEPTOR block on the first page."""
    start: float | None = None
    for line in lines:
        text = normalize(line.text)
        if start is None:
            tokens = text.split()
            if "EMISOR" in tokens and "RECEPTOR" in tokens:
                start = line.bottom
            continue
        if line.top <= start:
            continue
        if text.startswith(_PARTY_BLOCK_END) or ("CANTIDAD" in text and "DESCRIPCION" in text):
            return start, line.top
    if start is None:
        return None
    return start, page.height


def _column_fields(words: list[Word]) -> list[tuple[str, str]]:
    """(label, value) pairs of one column. Labels are right-aligned and end with ':'; values start at
    a common x. Lines with no label continue the previous value (wrapped addresses, long names)."""
    from .layout import group_lines

    lines = group_lines(words)
    value_starts: Counter[float] = Counter()
    for line in lines:
        for i, word in enumerate(line.words[:-1]):
            if word.text.endswith(":"):
                value_starts[round(line.words[i + 1].x0)] += 1
                break
    if not value_starts:
        return []
    value_x = value_starts.most_common(1)[0][0] - 1.5

    fields: list[tuple[str, str]] = []
    for line in lines:
        label = " ".join(w.text for w in line.words if w.x0 < value_x).strip()
        value = " ".join(w.text for w in line.words if w.x0 >= value_x).strip()
        if not label:
            if fields and value:
                prev_label, prev_value = fields[-1]
                fields[-1] = (prev_label, f"{prev_value} {value}".strip())
            continue
        fields.append((label, value))
    return fields


def _classify_id(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    return "dui" if len(digits) == 9 else "nit"


def _party(fields: list[tuple[str, str]], prefix: str) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for label, raw_value in fields:
        value = raw_value.strip() or None
        if value is not None and set(value) <= {"-"}:
            value = None
        key = normalize(label).rstrip(":").strip()
        if key.startswith("NOMBRE COMERCIAL") or key.startswith("NOMBRE DEL TERCERO"):
            continue
        if key.startswith("NOMBRE") or key.startswith("RAZON SOCIAL"):
            target = "nombre"
        elif key.startswith("NRC"):
            target = "nrc"
        elif "NIT" in key and "DUI" in key:
            target = _classify_id(value) if value else "nit"
        elif key.startswith("NIT"):
            target = "nit"
        elif key.startswith("DUI"):
            target = "dui"
        elif key in {"-", ""} or "DOCUMENTO" in key:
            if not value:
                continue
            target = _classify_id(value)
        else:
            continue
        if prefix == "emisor" and target == "dui":
            target = "nit"  # an emisor is always identified by NIT (a DUI-format NIT is still its NIT)
        name = f"{prefix}_{target}"
        if value and not out.get(name):
            out[name] = value
        else:
            out.setdefault(name, value)
    return out


def _parse_parties(page: Page, lines: list[Line]) -> dict[str, str | None]:
    block = _party_block(page, lines)
    if block is None:
        return {}
    top, bottom = block
    split = page.width / 2
    in_block = [w for w in page.words if w.top >= top - 0.5 and w.top < bottom - 0.5]
    left = [w for w in in_block if w.x0 < split]
    right = [w for w in in_block if w.x0 >= split]
    data: dict[str, str | None] = {}
    data.update(_party(_column_fields(left), "emisor"))
    data.update(_party(_column_fields(right), "receptor"))
    return data


# ------------------------------------------------------------------------------------------- amounts


def _last_match(lines: list[Line], pattern: re.Pattern[str]) -> re.Match[str] | None:
    found = None
    for line in lines:
        match = pattern.search(line.text)
        if match:
            found = match
    return found


def _missing_amount(field_name: str, label: str) -> Issue:
    return Issue(
        code="amount_not_found",
        severity=IssueSeverity.ERROR,
        message=f"No se encontró el monto '{label}' en el PDF.",
        field=field_name,
    )


def _parse_amounts(lines: list[Line], tipo: str | None, issues: list[Issue]) -> dict[str, Decimal]:
    data: dict[str, Decimal] = {}

    suma = _last_match(lines, _SUMA_VENTAS_RE)
    amounts = [parse_amount(a) for a in _AMOUNT_RE.findall(suma.group(1))] if suma else []
    if len(amounts) >= 3 and all(a is not None for a in amounts[-3:]):
        no_sujetas, exentas, gravadas = amounts[-3:]
        assert no_sujetas is not None and exentas is not None and gravadas is not None
        discounts = {"no sujetas": Decimal("0.00"), "exentas": Decimal("0.00"), "gravadas": Decimal("0.00")}
        for line in lines:
            match = _DESCUENTO_RE.search(line.text)
            if match:
                kind = re.sub(r"\s+", " ", match.group(1).lower())
                discounts[kind] = parse_amount(match.group(2)) or Decimal("0.00")
        data["total_no_sujetas"] = no_sujetas - discounts["no sujetas"]
        data["total_exentas"] = exentas - discounts["exentas"]
        data["total_gravadas"] = gravadas - discounts["gravadas"]
    else:
        issues.append(_missing_amount("total_gravadas", "Suma de Ventas (no sujetas, exentas, gravadas)"))

    total = _last_match(lines, _TOTAL_RE)
    total_value = parse_amount(total.group(1)) if total else None
    if total_value is None:
        issues.append(_missing_amount("total", "Monto Total de la Operación"))
    else:
        data["total"] = total_value

    retenido = _last_match(lines, _IVA_RETENIDO_RE)
    if retenido:
        data["iva_retenido"] = parse_amount(retenido.group(1)) or Decimal("0.00")

    if tipo in IVA_TIPOS:
        iva = _last_match(lines, _IVA_RE)
        iva_value = parse_amount(iva.group(1)) if iva else None
        if iva_value is not None:
            data["iva"] = iva_value
        elif data.get("total_gravadas", Decimal("0.00")) > 0:
            issues.append(_missing_amount("iva", "IVA 13%"))
    return data
