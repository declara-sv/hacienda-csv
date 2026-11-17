"""Shared domain contract between extraction, review, and anexo generation.

Every module that reads or writes DTE data goes through these types. Keep them free of
database and HTTP concerns so extraction and anexo generation stay pure and testable.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

ZERO = Decimal("0.00")


class TipoDte(StrEnum):
    """Código de tipo de documento DTE (catálogo CAT-002 del MH)."""

    FACTURA = "01"
    CCF = "03"
    NOTA_REMISION = "04"
    NOTA_CREDITO = "05"
    NOTA_DEBITO = "06"
    COMPROBANTE_RETENCION = "07"
    COMPROBANTE_LIQUIDACION = "08"
    DOCUMENTO_CONTABLE_LIQUIDACION = "09"
    FACTURA_EXPORTACION = "11"
    FACTURA_SUJETO_EXCLUIDO = "14"
    COMPROBANTE_DONACION = "15"


class ExtractionMethod(StrEnum):
    PARSER = "Parser"
    AI = "Ai"
    MANUAL = "Manual"


class IssueSeverity(StrEnum):
    WARNING = "Warning"
    ERROR = "Error"


class Issue(BaseModel):
    """A problem found in a document or in a generated anexo.

    Errors block generation until fixed or the document is excluded. Warnings are shown in the
    review table but do not block.
    """

    model_config = ConfigDict(frozen=True)

    code: str
    severity: IssueSeverity
    message: str
    field: str | None = None


class DteRecord(BaseModel):
    """One DTE as read from a PDF (or corrected by a user).

    Amounts are the document totals as printed. For a Factura (01) `total_gravadas` includes IVA
    and `iva` is 0. For CCF / NC / ND (03/05/06) `total_gravadas` excludes IVA and `iva` holds the
    débito fiscal.

    Identifier strings are stored exactly as printed (código de generación keeps its dashes,
    NIT/NRC keep whatever separators the PDF had). Normalization for the anexo happens in the
    anexo builder, never here.
    """

    tipo_dte: str = Field(description="Two-character code, e.g. '01', '03'.")
    codigo_generacion: str | None = None
    numero_control: str | None = None
    sello_recepcion: str | None = None
    fecha_emision: dt.date | None = None
    hora_emision: dt.time | None = None

    emisor_nombre: str | None = None
    emisor_nit: str | None = None
    emisor_nrc: str | None = None

    receptor_nombre: str | None = None
    receptor_nit: str | None = None
    receptor_nrc: str | None = None
    receptor_dui: str | None = None

    total_no_sujetas: Decimal = ZERO
    total_exentas: Decimal = ZERO
    total_gravadas: Decimal = ZERO
    iva: Decimal = ZERO
    iva_retenido: Decimal = ZERO
    total: Decimal = ZERO


class AiCallOutcome(StrEnum):
    USED = "used"  # the AI result became the documents
    DISCARDED = "discarded"  # a response came back but the parser result was kept (or it had no DTE)
    FAILED = "failed"  # the call or its output failed


class AiUsage(BaseModel):
    """One Claude API call made during extraction, recorded for the usage ledger.

    Token counts are None when no response was received (nothing is billed then).
    """

    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_creation_tokens: int | None = None
    duration_ms: int | None = None
    outcome: AiCallOutcome = AiCallOutcome.USED


class ExtractionResult(BaseModel):
    method: ExtractionMethod
    records: list[DteRecord]
    issues: list[Issue] = Field(default_factory=list)
    raw_text: str | None = None
    ai_calls: list[AiUsage] = Field(default_factory=list)
    page_count: int | None = None


class ClientProfile(BaseModel):
    """What the anexo builder and validators need to know about the client."""

    nit: str | None = None
    nrc: str | None = None
    default_tipo_operacion: str | None = None
    default_tipo_ingreso: str | None = None


class ReviewedDocument(BaseModel):
    """A DteRecord after review, as fed to the anexo builder."""

    id: str
    record: DteRecord
    tipo_operacion_renta: str | None = None
    tipo_ingreso_renta: str | None = None


class GeneratedCsv(BaseModel):
    anexo: int
    file_name: str
    content: bytes
    row_count: int


class AnexoBuildResult(BaseModel):
    files: list[GeneratedCsv]
    issues: list[Issue] = Field(default_factory=list)
