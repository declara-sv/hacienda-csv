"""Review table: DTE documents of a period, their issues and edits."""

from __future__ import annotations

import datetime as dt
import logging
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.errors import VALIDATION_TITLE, ApiError, validation_error
from app.api.schemas import DocumentBulkRequest, DocumentDto, DocumentPatchRequest, IssueDto
from app.domain import ClientProfile, DteRecord, Issue, IssueSeverity, ReviewedDocument
from app.models import Client, DocumentStatus, DteDocument, FilingPeriod
from app.services import integrations
from app.services.accounts import AccountContext
from app.services.ownership import owned_period

logger = logging.getLogger(__name__)

MONEY_FIELDS = ("total_no_sujetas", "total_exentas", "total_gravadas", "iva", "iva_retenido", "total")
RECORD_FIELDS = tuple(DteRecord.model_fields)
_CENT = Decimal("0.01")

_STRING_LIMITS = {
    "tipo_dte": 2,
    "codigo_generacion": 64,
    "numero_control": 64,
    "sello_recepcion": 64,
    "emisor_nombre": 250,
    "emisor_nit": 20,
    "emisor_nrc": 20,
    "receptor_nombre": 250,
    "receptor_nit": 20,
    "receptor_nrc": 20,
    "receptor_dui": 20,
}

CATALOG_KEYS = {"tipo_operacion": "tipoOperacion", "tipo_ingreso": "tipoIngreso"}


# --- Renta codes --------------------------------------------------------------------------------


def check_renta_code(kind: str, code: str | None, field: str) -> None:
    """Raise a 400 when `code` is not in RENTA_CATALOG[kind] (skipped if the catalog is unavailable)."""
    if code is None:
        return
    if not code.isdigit():
        raise validation_error(field, "El código debe ser numérico.")
    catalog = integrations.renta_catalog()
    if catalog is None:
        return
    entries = catalog.get(CATALOG_KEYS[kind]) or []
    codes = {str(entry.get("code")) for entry in entries if isinstance(entry, dict)}
    if codes and code not in codes:
        raise validation_error(field, "El código no existe en el catálogo de Renta.")


# --- Record <-> row -----------------------------------------------------------------------------


def record_from_document(doc: DteDocument) -> DteRecord:
    return DteRecord(**{name: getattr(doc, name) for name in RECORD_FIELDS})


def apply_record(doc: DteDocument, record: DteRecord) -> None:
    for name in RECORD_FIELDS:
        value = getattr(record, name)
        if name in MONEY_FIELDS:
            value = Decimal(value or 0).quantize(_CENT)
        elif isinstance(value, str):
            value = value.strip()[: _STRING_LIMITS.get(name, len(value))] or None
        setattr(doc, name, value)
    if not doc.tipo_dte:
        doc.tipo_dte = "00"


def client_profile(client: Client) -> ClientProfile:
    return ClientProfile(
        nit=client.nit,
        nrc=client.nrc,
        default_tipo_operacion=client.default_tipo_operacion,
        default_tipo_ingreso=client.default_tipo_ingreso,
    )


def effective_codes(doc: DteDocument, client: Client) -> tuple[str | None, str | None]:
    return (
        doc.tipo_operacion_renta or client.default_tipo_operacion,
        doc.tipo_ingreso_renta or client.default_tipo_ingreso,
    )


def reviewed_document(doc: DteDocument, client: Client) -> ReviewedDocument:
    operacion, ingreso = effective_codes(doc, client)
    return ReviewedDocument(
        id=str(doc.id),
        record=record_from_document(doc),
        tipo_operacion_renta=operacion,
        tipo_ingreso_renta=ingreso,
    )


# --- Issues -------------------------------------------------------------------------------------


def status_for(issues: list[Issue]) -> str:
    if any(i.severity == IssueSeverity.ERROR for i in issues):
        return DocumentStatus.ERROR.value
    if any(i.severity == IssueSeverity.WARNING for i in issues):
        return DocumentStatus.WARNING.value
    return DocumentStatus.OK.value


def _dedupe(issues: list[Issue]) -> list[Issue]:
    """Extraction and anexo validators overlap on some checks (e.g. IVA 13%); show each once."""
    seen: set[tuple] = set()
    result: list[Issue] = []
    for issue in issues:
        key = (issue.code, issue.field)
        if key not in seen:
            seen.add(key)
            result.append(issue)
    return result


def _safe(check, *args, **kwargs) -> list[Issue]:
    """A validator bug must not break the review table: report it as an Error on the document."""
    try:
        return list(check(*args, **kwargs))
    except Exception:
        logger.exception("Falló la validación %s.", getattr(check, "__name__", check))
        return [
            Issue(
                code="VALIDATION_FAILED",
                severity=IssueSeverity.ERROR,
                message="No se pudo validar el documento. Revise los datos o vuelva a leer el archivo.",
            )
        ]


def recompute_issues(docs: list[DteDocument], *, period: FilingPeriod, client: Client) -> None:
    """Recompute issues/status of every document of a period (duplicates depend on the whole set)."""
    profile = client_profile(client)
    try:
        duplicates = integrations.find_duplicate_codes(
            [(str(d.id), d.codigo_generacion) for d in docs if not d.excluded]
        )
    except Exception:
        logger.exception("Falló la detección de duplicados.")
        duplicates = {}
    for doc in docs:
        record = record_from_document(doc)
        issues: list[Issue] = []
        if not doc.edited:
            issues += [Issue.model_validate(i) for i in doc.extraction_issues or []]
        issues += _safe(integrations.validate_record, record)
        issues += _safe(
            integrations.validate_in_period, record, year=period.year, month=period.month, client=profile
        )
        if not doc.excluded:
            issues += duplicates.get(str(doc.id), [])
        issues += _safe(
            integrations.validate_for_anexo,
            reviewed_document(doc, client),
            year=period.year,
            month=period.month,
            client=profile,
        )
        issues = _dedupe(issues)
        serialized = [i.model_dump(mode="json") for i in issues]
        status = status_for(issues)
        if doc.issues != serialized:
            doc.issues = serialized
        if doc.status != status:
            doc.status = status


def period_documents(session: Session, period_id: uuid.UUID) -> list[DteDocument]:
    return list(
        session.scalars(
            select(DteDocument)
            .options(selectinload(DteDocument.upload))
            .where(DteDocument.filing_period_id == period_id)
            .order_by(
                DteDocument.fecha_emision.asc().nulls_last(),
                DteDocument.hora_emision.asc().nulls_last(),
                DteDocument.created_at_utc,
                DteDocument.id,
            )
        )
    )


def recompute_period(session: Session, period: FilingPeriod, client: Client) -> list[DteDocument]:
    docs = period_documents(session, period.id)
    recompute_issues(docs, period=period, client=client)
    return docs


def recompute_client(session: Session, client: Client) -> None:
    periods = session.scalars(
        select(FilingPeriod).where(
            FilingPeriod.client_id == client.id,
            FilingPeriod.id.in_(
                select(DteDocument.filing_period_id).where(DteDocument.client_id == client.id)
            ),
        )
    )
    for period in periods:
        recompute_period(session, period, client)


# --- DTOs ---------------------------------------------------------------------------------------


def _money(value: Decimal | None) -> str:
    return f"{Decimal(value or 0).quantize(_CENT):.2f}"


def _time(value: dt.time | None) -> str | None:
    return value.replace(microsecond=0).isoformat() if value is not None else None


def document_dto(doc: DteDocument, client: Client) -> DocumentDto:
    operacion, ingreso = effective_codes(doc, client)
    return DocumentDto(
        id=doc.id,
        upload_id=doc.upload_id,
        original_file_name=doc.upload.original_file_name,
        extraction_method=doc.extraction_method,
        status=doc.status,
        issues=[IssueDto.model_validate(i) for i in doc.issues or []],
        edited=doc.edited,
        excluded=doc.excluded,
        tipo_dte=doc.tipo_dte,
        codigo_generacion=doc.codigo_generacion,
        numero_control=doc.numero_control,
        sello_recepcion=doc.sello_recepcion,
        fecha_emision=doc.fecha_emision.isoformat() if doc.fecha_emision else None,
        hora_emision=_time(doc.hora_emision),
        emisor_nombre=doc.emisor_nombre,
        emisor_nit=doc.emisor_nit,
        emisor_nrc=doc.emisor_nrc,
        receptor_nombre=doc.receptor_nombre,
        receptor_nit=doc.receptor_nit,
        receptor_nrc=doc.receptor_nrc,
        receptor_dui=doc.receptor_dui,
        total_no_sujetas=_money(doc.total_no_sujetas),
        total_exentas=_money(doc.total_exentas),
        total_gravadas=_money(doc.total_gravadas),
        iva=_money(doc.iva),
        iva_retenido=_money(doc.iva_retenido),
        total=_money(doc.total),
        tipo_operacion_renta=doc.tipo_operacion_renta,
        tipo_ingreso_renta=doc.tipo_ingreso_renta,
        effective_tipo_operacion=operacion,
        effective_tipo_ingreso=ingreso,
        anexo=integrations.anexo_for_tipo(doc.tipo_dte),
    )


# --- Use cases ----------------------------------------------------------------------------------


def list_documents(
    session: Session, client_id: uuid.UUID, period_id: uuid.UUID, account: AccountContext
) -> list[DocumentDto]:
    client, period = owned_period(session, client_id, period_id, account.account_id)
    docs = recompute_period(session, period, client)
    session.commit()
    return [document_dto(d, client) for d in docs]


def update_document(
    session: Session,
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    document_id: uuid.UUID,
    account: AccountContext,
    request: DocumentPatchRequest,
) -> DocumentDto:
    client, period = owned_period(session, client_id, period_id, account.account_id)
    doc = session.scalar(
        select(DteDocument).where(DteDocument.id == document_id, DteDocument.filing_period_id == period.id)
    )
    if doc is None:
        raise ApiError(404)

    changes = request.model_dump(exclude_unset=True)
    if "tipo_dte" in changes and changes["tipo_dte"] is None:
        raise validation_error("tipoDte", "El campo es requerido.")
    for field in MONEY_FIELDS:
        if field in changes and changes[field] is None:
            raise validation_error(_camel(field), "El campo es requerido.")
    if "excluded" in changes and changes["excluded"] is None:
        raise validation_error("excluded", "El campo es requerido.")
    if "tipo_operacion_renta" in changes:
        check_renta_code("tipo_operacion", changes["tipo_operacion_renta"], "tipoOperacionRenta")
    if "tipo_ingreso_renta" in changes:
        check_renta_code("tipo_ingreso", changes["tipo_ingreso_renta"], "tipoIngresoRenta")

    record_changed = False
    for field, value in changes.items():
        if field in RECORD_FIELDS:
            if field in MONEY_FIELDS:
                value = Decimal(value).quantize(_CENT)
            if getattr(doc, field) != value:
                setattr(doc, field, value)
                record_changed = True
        else:
            setattr(doc, field, value)
    if record_changed:
        doc.edited = True
    if changes:
        doc.updated_at_utc = dt.datetime.now(dt.UTC)

    session.flush()
    docs = recompute_period(session, period, client)
    session.commit()
    updated = next(d for d in docs if d.id == doc.id)
    return document_dto(updated, client)


def bulk_update(
    session: Session,
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    account: AccountContext,
    request: DocumentBulkRequest,
) -> list[DocumentDto]:
    client, period = owned_period(session, client_id, period_id, account.account_id)
    changes = request.model_dump(exclude_unset=True, exclude={"document_ids"})
    if not changes:
        raise ApiError(400, VALIDATION_TITLE, {"changes": ["Indique al menos un cambio."]})
    if "excluded" in changes and changes["excluded"] is None:
        raise validation_error("excluded", "El campo es requerido.")
    if "tipo_operacion_renta" in changes:
        check_renta_code("tipo_operacion", changes["tipo_operacion_renta"], "tipoOperacionRenta")
    if "tipo_ingreso_renta" in changes:
        check_renta_code("tipo_ingreso", changes["tipo_ingreso_renta"], "tipoIngresoRenta")

    ids = set(request.document_ids)
    docs = list(
        session.scalars(
            select(DteDocument).where(DteDocument.id.in_(ids), DteDocument.filing_period_id == period.id)
        )
    )
    if len(docs) != len(ids):
        raise validation_error("documentIds", "Uno o más documentos no pertenecen a este período.")

    now = dt.datetime.now(dt.UTC)
    for doc in docs:
        for field, value in changes.items():
            setattr(doc, field, value)
        doc.updated_at_utc = now

    session.flush()
    all_docs = recompute_period(session, period, client)
    session.commit()
    return [document_dto(d, client) for d in all_docs]


def _camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(p.title() for p in rest)
