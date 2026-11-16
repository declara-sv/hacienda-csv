"""Small rules shared by the anexo validator and builder."""

from __future__ import annotations

from app.anexos.catalog import RENTA_VALUE_BEFORE_REQUIRED, renta_required
from app.domain import ClientProfile, ReviewedDocument, TipoDte

_ANEXO_BY_TIPO: dict[str, int] = {
    TipoDte.FACTURA: 2,
    TipoDte.CCF: 1,
    TipoDte.NOTA_CREDITO: 1,
    TipoDte.NOTA_DEBITO: 1,
}


def anexo_for_tipo(tipo_dte: str) -> int | None:
    """Sales anexo a DTE type goes to: 2 for Factura (01), 1 for CCF/NC/ND (03/05/06), else None."""
    return _ANEXO_BY_TIPO.get((tipo_dte or "").strip())


def _clean(code: str | None) -> str | None:
    code = (code or "").strip()
    return code or None


def effective_renta_codes(document: ReviewedDocument, client: ClientProfile) -> tuple[str | None, str | None]:
    """(tipo operación, tipo ingreso): the document override, else the client default."""
    operacion = _clean(document.tipo_operacion_renta) or _clean(client.default_tipo_operacion)
    ingreso = _clean(document.tipo_ingreso_renta) or _clean(client.default_tipo_ingreso)
    return operacion, ingreso


def renta_output_codes(
    document: ReviewedDocument, client: ClientProfile, *, year: int, month: int
) -> tuple[str, str]:
    """Values written to the anexo Renta columns: effective codes from 2025-01, "0" before."""
    if not renta_required(year, month):
        return RENTA_VALUE_BEFORE_REQUIRED, RENTA_VALUE_BEFORE_REQUIRED
    operacion, ingreso = effective_renta_codes(document, client)
    return operacion or "", ingreso or ""


def check_period(year: int, month: int) -> None:
    if not 1 <= month <= 12:
        raise ValueError(f"mes inválido: {month}")
    if not 2000 <= year <= 9999:
        raise ValueError(f"año inválido: {year}")
