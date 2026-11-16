"""HTTP request/response models. JSON is camelCase; datetimes are ISO-8601 UTC (`...Z`)."""

from __future__ import annotations

import datetime as dt
import re
import uuid
from decimal import Decimal
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
)
from pydantic.alias_generators import to_camel


def _iso_utc(value: dt.datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.UTC)
    return value.astimezone(dt.UTC).isoformat().replace("+00:00", "Z")


UtcDateTime = Annotated[dt.datetime, PlainSerializer(_iso_utc, return_type=str)]


def _blank_to_none(value: object) -> object:
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def _strip(value: object) -> object:
    return value.strip() if isinstance(value, str) else value


_TAX_ID_RE = re.compile(r"^[0-9]+(-[0-9]+)*$")


def _tax_number(value: str | None) -> str | None:
    if value is not None and not _TAX_ID_RE.match(value):
        raise ValueError("Solo se permiten dígitos y guiones.")
    return value


def _email(value: str) -> str:
    # Same rule as .NET's [EmailAddress]: a single "@" that is neither first nor last.
    at = value.find("@")
    if at <= 0 or at == len(value) - 1 or at != value.rfind("@") or any(c.isspace() for c in value):
        raise ValueError("El correo electrónico no es válido.")
    return value


def required_str(max_length: int, min_length: int = 1):
    return Annotated[str, BeforeValidator(_strip), Field(min_length=min_length, max_length=max_length)]


def optional_str(max_length: int, pattern: str | None = None):
    inner = Annotated[str, Field(max_length=max_length, pattern=pattern)]
    return Annotated[inner | None, BeforeValidator(_blank_to_none), Field(default=None)]


TaxNumber = Annotated[
    Annotated[str, Field(max_length=20), AfterValidator(_tax_number)] | None,
    BeforeValidator(_blank_to_none),
    Field(default=None),
]
RentaCode = optional_str(2)
Email = Annotated[str, BeforeValidator(_strip), Field(min_length=1, max_length=320), AfterValidator(_email)]


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


# --- Auth ---------------------------------------------------------------------------------------


class RegisterRequest(ApiModel):
    email: Email
    password: Annotated[str, Field(min_length=8, max_length=128)]
    full_name: required_str(200)


class LoginRequest(ApiModel):
    email: Email
    password: Annotated[str, Field(min_length=8, max_length=128)]


class RefreshRequest(ApiModel):
    refresh_token: Annotated[str, Field(min_length=30, max_length=400)]


class AuthAccountDto(ApiModel):
    id: uuid.UUID
    name: str
    role: str


class AuthUserDto(ApiModel):
    id: uuid.UUID
    email: str
    full_name: str
    # The user's default account (additive; older clients ignore it).
    account: AuthAccountDto | None = None


class AuthResponseDto(ApiModel):
    access_token: str
    access_token_expires_at_utc: UtcDateTime
    refresh_token: str
    user: AuthUserDto


# --- Clients ------------------------------------------------------------------------------------


class ClientRequest(ApiModel):
    name: required_str(160)
    tax_id: required_str(32)
    notes: optional_str(2000)
    nit: TaxNumber
    nrc: TaxNumber
    default_tipo_operacion: RentaCode
    default_tipo_ingreso: RentaCode


class ClientConfigDto(ApiModel):
    id: uuid.UUID
    name: str
    prefill_values_json: str
    transformation_rules_json: str | None
    is_active: bool
    updated_at_utc: UtcDateTime


class FilingPeriodSummaryDto(ApiModel):
    id: uuid.UUID
    year: int
    month: int
    created_at_utc: UtcDateTime


class ClientSummaryDto(ApiModel):
    id: uuid.UUID
    name: str
    tax_id: str
    nit: str | None
    nrc: str | None
    default_tipo_operacion: str | None
    default_tipo_ingreso: str | None
    filing_periods_count: int
    created_at_utc: UtcDateTime


class ClientDetailDto(ApiModel):
    id: uuid.UUID
    name: str
    tax_id: str
    notes: str | None
    nit: str | None
    nrc: str | None
    default_tipo_operacion: str | None
    default_tipo_ingreso: str | None
    created_at_utc: UtcDateTime
    configurations: list[ClientConfigDto]
    filing_periods: list[FilingPeriodSummaryDto]


class ClientConfigRequest(ApiModel):
    name: required_str(80)
    prefill_values_json: str = "{}"
    transformation_rules_json: str | None = None
    is_active: bool = False


# --- Filing periods -----------------------------------------------------------------------------


class FilingPeriodRequest(ApiModel):
    year: Annotated[int, Field(ge=2000, le=2100)]
    month: Annotated[int, Field(ge=1, le=12)]


class FilingPeriodDto(ApiModel):
    id: uuid.UUID
    year: int
    month: int
    created_at_utc: UtcDateTime
    uploads_count: int


# --- Uploads ------------------------------------------------------------------------------------


class UploadDto(ApiModel):
    id: uuid.UUID
    filing_period_id: uuid.UUID
    original_file_name: str
    source_file_kind: str
    content_type: str
    size_bytes: int
    created_at_utc: UtcDateTime
    included_in_latest_run: bool
    extraction_status: str
    extraction_error: str | None
    documents_count: int


# --- Documents ----------------------------------------------------------------------------------


class IssueDto(ApiModel):
    code: str
    severity: str
    message: str
    field: str | None = None


class DocumentDto(ApiModel):
    id: uuid.UUID
    upload_id: uuid.UUID
    original_file_name: str
    extraction_method: str
    status: str
    issues: list[IssueDto]
    edited: bool
    excluded: bool
    tipo_dte: str
    codigo_generacion: str | None
    numero_control: str | None
    sello_recepcion: str | None
    fecha_emision: str | None
    hora_emision: str | None
    emisor_nombre: str | None
    emisor_nit: str | None
    emisor_nrc: str | None
    receptor_nombre: str | None
    receptor_nit: str | None
    receptor_nrc: str | None
    receptor_dui: str | None
    total_no_sujetas: str
    total_exentas: str
    total_gravadas: str
    iva: str
    iva_retenido: str
    total: str
    tipo_operacion_renta: str | None
    tipo_ingreso_renta: str | None
    effective_tipo_operacion: str | None
    effective_tipo_ingreso: str | None
    anexo: int | None


Money = Annotated[Decimal, Field(ge=0, le=Decimal("999999999999.99"), allow_inf_nan=False)]


class DocumentPatchRequest(ApiModel):
    """Only the fields present in the body are changed; null clears a nullable field."""

    tipo_dte: optional_str(2, r"^\d{2}$")
    codigo_generacion: optional_str(64)
    numero_control: optional_str(64)
    sello_recepcion: optional_str(64)
    fecha_emision: dt.date | None = None
    hora_emision: dt.time | None = None
    emisor_nombre: optional_str(250)
    emisor_nit: optional_str(20)
    emisor_nrc: optional_str(20)
    receptor_nombre: optional_str(250)
    receptor_nit: optional_str(20)
    receptor_nrc: optional_str(20)
    receptor_dui: optional_str(20)
    total_no_sujetas: Money | None = None
    total_exentas: Money | None = None
    total_gravadas: Money | None = None
    iva: Money | None = None
    iva_retenido: Money | None = None
    total: Money | None = None
    excluded: bool | None = None
    tipo_operacion_renta: RentaCode
    tipo_ingreso_renta: RentaCode


class DocumentBulkRequest(ApiModel):
    document_ids: Annotated[list[uuid.UUID], Field(min_length=1, max_length=5000)]
    tipo_operacion_renta: RentaCode
    tipo_ingreso_renta: RentaCode
    excluded: bool | None = None


# --- Generation runs ----------------------------------------------------------------------------


class OutputArtifactDto(ApiModel):
    id: uuid.UUID
    artifact_kind: str
    file_name: str
    created_at_utc: UtcDateTime
    size_bytes: int
    row_count: int | None


class GenerationRunFileDto(ApiModel):
    upload_id: uuid.UUID | None
    original_file_name: str
    source_file_kind: str
    status: str
    error_message: str | None


class GenerationRunDto(ApiModel):
    id: uuid.UUID
    filing_period_id: uuid.UUID
    version: int
    status: str
    error_message: str | None
    created_at_utc: UtcDateTime
    started_at_utc: UtcDateTime | None
    completed_at_utc: UtcDateTime | None
    files: list[GenerationRunFileDto]
    artifacts: list[OutputArtifactDto]
    issues: list[IssueDto]


# --- Usage --------------------------------------------------------------------------------------


class UsageDocumentsDto(ApiModel):
    parser: int = 0
    ai: int = 0
    manual: int = 0
    total: int = 0


class UsageTotalsDto(ApiModel):
    """Usage of one client (or the whole account when `clientId` is null) in a month."""

    client_id: uuid.UUID | None = None
    client_name: str | None = None
    uploads: int = 0
    bytes_stored: int = 0
    documents_extracted: UsageDocumentsDto = Field(default_factory=UsageDocumentsDto)
    extractions_failed: int = 0
    ai_calls: int = 0
    ai_input_tokens: int = 0
    ai_output_tokens: int = 0
    ai_cache_read_tokens: int = 0
    ai_cache_creation_tokens: int = 0
    ai_cost_usd: str = "0.000000"
    # AI calls with tokens but no price (model missing from the price table).
    ai_calls_unpriced: int = 0
    runs: int = 0
    rows_generated: int = 0
    downloads: int = 0


class UsageReportDto(ApiModel):
    year: int
    month: int
    clients: list[UsageTotalsDto]
    total: UsageTotalsDto
