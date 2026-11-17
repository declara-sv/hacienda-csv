"""AI fallback: read a DTE PDF with Claude when the deterministic parser cannot.

The client is injected so tests can use a fake; nothing here runs at import time against the API.
"""

from __future__ import annotations

import base64
import time
from dataclasses import dataclass
from typing import Any, Protocol

import anthropic
import pydantic
from pydantic import BaseModel, ConfigDict, Field

from app.domain import AiCallOutcome, AiUsage, DteRecord

from .mh_parser import parse_amount, parse_date, parse_time


@dataclass
class AiExtractorOutput:
    records: list[DteRecord]
    usage: AiUsage | None = None


class AiExtractor(Protocol):
    def extract(self, pdf_bytes: bytes) -> AiExtractorOutput: ...


class AiExtractionError(Exception):
    """The AI extractor could not produce a result (API error, refusal, truncated or invalid output).

    `usage` describes the call that failed. It carries token counts whenever a response was received,
    because those tokens are billed even though the output is unusable.
    """

    def __init__(self, message: str, usage: AiUsage | None = None) -> None:
        super().__init__(message)
        self.usage = usage


class AiDocument(BaseModel):
    """Output schema for one DTE. Amounts, dates and times are strings so values are copied exactly."""

    model_config = ConfigDict(extra="forbid")

    tipo_dte: str = Field(description="Código de tipo de DTE de dos dígitos: 01, 03, 05, 06, ...")
    codigo_generacion: str | None = Field(description="Código de Generación exactamente como aparece.")
    numero_control: str | None = Field(description="Número de Control exactamente como aparece.")
    sello_recepcion: str | None = Field(description="Sello de Recepción exactamente como aparece.")
    fecha_emision: str | None = Field(description="Fecha de emisión/generación en formato YYYY-MM-DD.")
    hora_emision: str | None = Field(description="Hora de emisión/generación en formato HH:MM:SS.")
    emisor_nombre: str | None
    emisor_nit: str | None = Field(description="NIT del emisor tal como aparece, con sus guiones.")
    emisor_nrc: str | None = Field(description="NRC del emisor tal como aparece, con sus guiones.")
    receptor_nombre: str | None
    receptor_nit: str | None = Field(description="NIT del receptor tal como aparece, con sus guiones.")
    receptor_nrc: str | None = Field(description="NRC del receptor tal como aparece, con sus guiones.")
    receptor_dui: str | None = Field(description="DUI del receptor (persona natural) tal como aparece.")
    total_no_sujetas: str = Field(description="Total de ventas no sujetas, p. ej. '0.00'.")
    total_exentas: str = Field(description="Total de ventas exentas, p. ej. '2.50'.")
    total_gravadas: str = Field(description="Total de ventas gravadas según la convención del tipo de DTE.")
    iva: str = Field(description="IVA 13% (débito fiscal); '0.00' para facturas (01).")
    iva_retenido: str = Field(description="IVA retenido; '0.00' si no hay.")
    total: str = Field(description="Monto Total de la Operación.")


class AiExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    documents: list[AiDocument] = Field(description="Un elemento por cada DTE en el PDF.")


PROMPT = """\
The attached PDF contains one or more electronic tax documents (Documentos Tributarios Electrónicos, \
DTE) from El Salvador. Extract every DTE in the file, one entry per document. A document can span \
several pages; a new document starts where a new "Código de Generación" appears.

Fields:
- tipo_dte: two-digit type code from the title or from the "DTE-NN-" prefix of the Número de Control: \
01 Factura, 03 Comprobante de Crédito Fiscal, 04 Nota de Remisión, 05 Nota de Crédito, 06 Nota de \
Débito, 07 Comprobante de Retención, 08 Comprobante de Liquidación, 09 Documento Contable de \
Liquidación, 11 Factura de Exportación, 14 Factura de Sujeto Excluido, 15 Comprobante de Donación.
- codigo_generacion: "Código de Generación", a UUID like 0A1B2C3D-4E5F-4A6B-8C7D-9E0F1A2B3C4D.
- numero_control: "Número de Control", like DTE-01-M001P001-000000000000101.
- sello_recepcion: "Sello de Recepción" (the reception stamp from Hacienda).
- fecha_emision / hora_emision: "Fecha y Hora de Generación" (or "Fecha de Emisión"), as YYYY-MM-DD \
and HH:MM:SS.
- emisor_*: the issuer (EMISOR block). receptor_*: the recipient (RECEPTOR block). Use receptor_dui \
only when the recipient is identified by a DUI; use receptor_nit for a NIT.
- Amounts: total_no_sujetas, total_exentas, total_gravadas (the "Ventas No Sujetas", "Ventas Exentas" \
and "Ventas Gravadas" totals, after any global discount), iva, iva_retenido, total ("Monto Total de la \
Operación").

Rules:
- Copy identifiers exactly as printed, character by character. Keep the dashes in the código de \
generación, número de control, NIT, NRC and DUI. Do not reformat, pad or remove separators.
- Factura (01): prices include IVA. total_gravadas is the printed gravadas total (IVA included) and \
iva is "0.00".
- Comprobante de Crédito Fiscal (03), Nota de Crédito (05), Nota de Débito (06): total_gravadas \
excludes IVA, and iva is the printed IVA 13% amount (débito fiscal).
- Write amounts as plain decimal numbers with two decimals and a dot, without currency symbols or \
thousands separators, e.g. "1234.50". Use "0.00" when an amount is not printed.
- Use null for a text field that is empty, shown as "-", or not present. Never guess or invent values.
- If the file contains no DTE at all, return an empty documents list.
"""

_OK_STOP_REASONS = {"end_turn", "stop_sequence"}


def _text(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value or set(value) <= {"-"} or value.lower() in {"null", "none", "n/a"}:
        return None
    return value


def _amount(value: str, name: str) -> Any:
    parsed = parse_amount(value)
    if parsed is None:
        raise AiExtractionError(f"La IA devolvió un monto inválido en {name}: {value!r}.")
    return parsed


def to_record(doc: AiDocument) -> DteRecord:
    tipo = (doc.tipo_dte or "").strip()
    if tipo.isdigit() and len(tipo) == 1:
        tipo = f"0{tipo}"
    return DteRecord(
        tipo_dte=tipo,
        codigo_generacion=_text(doc.codigo_generacion),
        numero_control=_text(doc.numero_control),
        sello_recepcion=_text(doc.sello_recepcion),
        fecha_emision=parse_date(_text(doc.fecha_emision)),
        hora_emision=parse_time(_text(doc.hora_emision)),
        emisor_nombre=_text(doc.emisor_nombre),
        emisor_nit=_text(doc.emisor_nit),
        emisor_nrc=_text(doc.emisor_nrc),
        receptor_nombre=_text(doc.receptor_nombre),
        receptor_nit=_text(doc.receptor_nit),
        receptor_nrc=_text(doc.receptor_nrc),
        receptor_dui=_text(doc.receptor_dui),
        total_no_sujetas=_amount(doc.total_no_sujetas, "total_no_sujetas"),
        total_exentas=_amount(doc.total_exentas, "total_exentas"),
        total_gravadas=_amount(doc.total_gravadas, "total_gravadas"),
        iva=_amount(doc.iva, "iva"),
        iva_retenido=_amount(doc.iva_retenido, "iva_retenido"),
        total=_amount(doc.total, "total"),
    )


_OUTPUT_CONFIG = {"format": {"type": "json_schema", "schema": anthropic.transform_schema(AiExtraction)}}


def _token(usage: Any, name: str) -> int:
    value = getattr(usage, name, None) if usage is not None else None
    return int(value) if isinstance(value, int) else 0


def _response_text(response: Any) -> str | None:
    for block in getattr(response, "content", None) or []:
        if getattr(block, "type", None) == "text":
            return getattr(block, "text", None)
    return None


class ClaudeAiExtractor:
    """AiExtractor backed by the Anthropic Messages API with structured output.

    Uses `messages.create` and validates the JSON here (instead of `messages.parse`) so token usage
    is available even when the output is a refusal or does not match the schema.
    """

    def __init__(self, client: Any, model: str, *, max_tokens: int = 16000) -> None:
        self._client = client
        self._model = model
        self._max_tokens = max_tokens

    @property
    def model(self) -> str:
        return self._model

    def _usage(self, response: Any, started: float, outcome: AiCallOutcome) -> AiUsage:
        duration_ms = int((time.monotonic() - started) * 1000)
        if response is None:
            return AiUsage(model=self._model, duration_ms=duration_ms, outcome=outcome)
        usage = getattr(response, "usage", None)
        return AiUsage(
            model=self._model,
            input_tokens=_token(usage, "input_tokens"),
            output_tokens=_token(usage, "output_tokens"),
            cache_read_tokens=_token(usage, "cache_read_input_tokens"),
            cache_creation_tokens=_token(usage, "cache_creation_input_tokens"),
            duration_ms=duration_ms,
            outcome=outcome,
        )

    def extract(self, pdf_bytes: bytes) -> AiExtractorOutput:
        data = base64.standard_b64encode(pdf_bytes).decode("ascii")
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {"type": "base64", "media_type": "application/pdf", "data": data},
                    },
                    {"type": "text", "text": PROMPT},
                ],
            }
        ]
        started = time.monotonic()
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                messages=messages,
                output_config=_OUTPUT_CONFIG,
            )
        except anthropic.APIStatusError as exc:
            message = f"Error del servicio de IA (HTTP {exc.status_code})."
            raise AiExtractionError(message, self._usage(None, started, AiCallOutcome.FAILED)) from exc
        except anthropic.APIConnectionError as exc:
            message = "No se pudo conectar con el servicio de IA."
            raise AiExtractionError(message, self._usage(None, started, AiCallOutcome.FAILED)) from exc
        except anthropic.AnthropicError as exc:
            message = f"Error del servicio de IA ({type(exc).__name__})."
            raise AiExtractionError(message, self._usage(None, started, AiCallOutcome.FAILED)) from exc
        except ValueError as exc:  # e.g. an undecodable response body
            message = "La IA devolvió una respuesta con formato inválido."
            raise AiExtractionError(message, self._usage(None, started, AiCallOutcome.FAILED)) from exc

        try:
            records = self._records(response)
        except AiExtractionError as exc:
            exc.usage = self._usage(response, started, AiCallOutcome.FAILED)
            raise
        return AiExtractorOutput(records, self._usage(response, started, AiCallOutcome.USED))

    def _records(self, response: Any) -> list[DteRecord]:
        stop_reason = getattr(response, "stop_reason", None)
        if stop_reason == "refusal":
            raise AiExtractionError("La IA se negó a procesar el documento.")
        if stop_reason == "max_tokens":
            raise AiExtractionError("La respuesta de la IA quedó incompleta (límite de tokens).")
        if stop_reason not in _OK_STOP_REASONS:
            raise AiExtractionError(f"La IA terminó de forma inesperada ({stop_reason}).")

        text = _response_text(response)
        if not text:
            raise AiExtractionError("La IA no devolvió datos estructurados.")
        try:
            parsed = AiExtraction.model_validate_json(text)
        except (pydantic.ValidationError, ValueError) as exc:
            raise AiExtractionError("La IA devolvió una respuesta con formato inválido.") from exc
        return [to_record(doc) for doc in parsed.documents]


def build_ai_extractor(settings: Any) -> AiExtractor | None:
    """Claude-backed extractor from settings, or None when AI extraction is disabled or has no key."""
    if not getattr(settings, "ai_extraction_enabled", False):
        return None
    api_key = (getattr(settings, "anthropic_api_key", "") or "").strip()
    if not api_key:
        return None
    client = anthropic.Anthropic(api_key=api_key)
    return ClaudeAiExtractor(client, settings.ai_extraction_model)
