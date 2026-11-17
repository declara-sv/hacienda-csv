"""Value normalization shared by the anexo validator and the CSV writer."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from app.domain import Issue, IssueSeverity, ReviewedDocument

CENT = Decimal("0.01")
_NON_DIGITS = re.compile(r"\D")
_WHITESPACE = re.compile(r"\s+")


def money(value: Decimal | int | str | None) -> Decimal:
    """Amount quantized to 2 decimals, ROUND_HALF_UP. None counts as 0."""
    if value is None or value == "":
        return Decimal("0.00")
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def digits(value: str | None) -> str:
    return _NON_DIGITS.sub("", value or "")


def document_label(document: ReviewedDocument) -> str:
    record = document.record
    return record.codigo_generacion or record.numero_control or document.id


def with_prefix(issue: Issue, label: str) -> Issue:
    return issue.model_copy(update={"message": f"Documento {label}: {issue.message}"})


def sanitize_text(value: str, *, field_name: str, encoding: str, delimiter: str) -> tuple[str, list[Issue]]:
    """Make a text value safe for a delimited, single-byte-encoded line.

    Collapses whitespace (incl. line breaks), replaces the delimiter, and replaces characters the
    encoding cannot represent (first by their unaccented base letter, else ``?``). Each change that
    alters visible content produces a Warning.
    """
    issues: list[Issue] = []
    text = _WHITESPACE.sub(" ", value).strip()

    if delimiter in text:
        replacement = "," if delimiter != "," else " "
        text = text.replace(delimiter, replacement)
        issues.append(
            Issue(
                code="delimiter_in_text",
                severity=IssueSeverity.WARNING,
                message=f"el campo contenía el separador {delimiter!r}; se reemplazó por {replacement!r}.",
                field=field_name,
            )
        )

    bad: list[str] = []
    out: list[str] = []
    for ch in text:
        if _encodable(ch, encoding):
            out.append(ch)
            continue
        bad.append(ch)
        base = "".join(c for c in unicodedata.normalize("NFKD", ch) if not unicodedata.combining(c))
        out.append(base if base and _encodable(base, encoding) else "?")
    if bad:
        shown = " ".join(dict.fromkeys(bad))
        issues.append(
            Issue(
                code="character_not_encodable",
                severity=IssueSeverity.WARNING,
                message=f"caracteres no representables en {encoding} reemplazados: {shown}",
                field=field_name,
            )
        )
    return "".join(out), issues


def _encodable(text: str, encoding: str) -> bool:
    try:
        text.encode(encoding)
    except UnicodeEncodeError:
        return False
    return True


@dataclass
class ReceptorId:
    """Anexo 1 receptor identification: H (NIT/NRC) and Q (DUI) are mutually exclusive."""

    nit_nrc: str = ""
    dui: str = ""
    issues: list[Issue] = field(default_factory=list)


def normalize_receptor(nit: str | None, dui: str | None, nrc: str | None) -> ReceptorId:
    """NIT: 14 digits as-is, 13 left-padded with 0, 9 = DUI homologado (goes to DUI).

    Without NIT: DUI with 9 digits (8 left-padded). Without either: NRC as printed (digits only)
    with a Warning. Otherwise an Error.
    """
    nit_raw = (nit or "").strip()
    if nit_raw:
        nit_digits = digits(nit_raw)
        if len(nit_digits) == 14:
            return ReceptorId(nit_nrc=nit_digits)
        if len(nit_digits) == 13:
            return ReceptorId(nit_nrc="0" + nit_digits)
        if len(nit_digits) == 9:
            return ReceptorId(dui=nit_digits)
        return ReceptorId(
            issues=[
                Issue(
                    code="invalid_receptor_nit",
                    severity=IssueSeverity.ERROR,
                    message=(
                        f"el NIT del receptor {nit_raw!r} no tiene 14 dígitos (ni 13 para completar con 0, "
                        "ni 9 de un DUI homologado)."
                    ),
                    field="receptor_nit",
                )
            ]
        )

    dui_raw = (dui or "").strip()
    if dui_raw:
        dui_digits = digits(dui_raw)
        if len(dui_digits) == 9:
            return ReceptorId(dui=dui_digits)
        if len(dui_digits) == 8:
            return ReceptorId(dui="0" + dui_digits)
        return ReceptorId(
            issues=[
                Issue(
                    code="invalid_receptor_dui",
                    severity=IssueSeverity.ERROR,
                    message=f"el DUI del receptor {dui_raw!r} no tiene 9 dígitos.",
                    field="receptor_dui",
                )
            ]
        )

    nrc_digits = digits(nrc)
    if nrc_digits:
        return ReceptorId(
            nit_nrc=nrc_digits,
            issues=[
                Issue(
                    code="receptor_nrc_used",
                    severity=IssueSeverity.WARNING,
                    message="el receptor no tiene NIT ni DUI; se reporta su NRC en la columna H.",
                    field="receptor_nrc",
                )
            ],
        )

    return ReceptorId(
        issues=[
            Issue(
                code="missing_receptor_id",
                severity=IssueSeverity.ERROR,
                message="falta el NIT, DUI o NRC del receptor (requerido en el Anexo 1).",
                field="receptor_nit",
            )
        ]
    )
