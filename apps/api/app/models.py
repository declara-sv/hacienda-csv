"""Database models. Table names match the previous .NET schema; columns are snake_case."""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


Money = Numeric(14, 2)


class RunStatus(StrEnum):
    PENDING = "Pending"
    RUNNING = "Running"
    COMPLETED = "Completed"
    FAILED = "Failed"


class RunFileStatus(StrEnum):
    PENDING = "Pending"
    INCLUDED = "Included"
    FAILED = "Failed"


class ExtractionStatus(StrEnum):
    PENDING = "Pending"
    RUNNING = "Running"
    COMPLETED = "Completed"
    FAILED = "Failed"


class DocumentStatus(StrEnum):
    OK = "Ok"
    WARNING = "Warning"
    ERROR = "Error"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320))
    normalized_email: Mapped[str] = mapped_column(String(320), unique=True)
    full_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(2048))
    created_at_utc: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(200), unique=True)
    created_at_utc: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at_utc: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    revoked_at_utc: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class Client(Base):
    __tablename__ = "clients"
    __table_args__ = (Index("ix_clients_owner_name", "owner_user_id", "name"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(160))
    # Legacy free-form identifier shown in the UI. `nit` / `nrc` are the structured values used
    # to recognise the client as emisor of a DTE.
    tax_id: Mapped[str] = mapped_column(String(32))
    nit: Mapped[str | None] = mapped_column(String(20))
    nrc: Mapped[str | None] = mapped_column(String(20))
    # Renta codes applied to every document unless overridden per document (F-07 since 01/2025).
    default_tipo_operacion: Mapped[str | None] = mapped_column(String(2))
    default_tipo_ingreso: Mapped[str | None] = mapped_column(String(2))
    notes: Mapped[str | None] = mapped_column(String(2000))
    created_at_utc: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    configurations: Mapped[list[ClientConfig]] = relationship(
        back_populates="client", cascade="all, delete-orphan", passive_deletes=True
    )
    filing_periods: Mapped[list[FilingPeriod]] = relationship(
        back_populates="client", cascade="all, delete-orphan", passive_deletes=True
    )


class ClientConfig(Base):
    __tablename__ = "client_configs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80), default="Base")
    prefill_values_json: Mapped[str] = mapped_column(Text, default="{}")
    transformation_rules_json: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at_utc: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at_utc: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    client: Mapped[Client] = relationship(back_populates="configurations")


class FilingPeriod(Base):
    __tablename__ = "filing_periods"
    __table_args__ = (
        UniqueConstraint("client_id", "year", "month", name="uq_filing_periods_client_year_month"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"))
    year: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)
    created_at_utc: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    client: Mapped[Client] = relationship(back_populates="filing_periods")


class Upload(Base):
    __tablename__ = "uploads"
    __table_args__ = (
        Index("ix_uploads_period_created", "client_id", "filing_period_id", "created_at_utc"),
        Index("ix_uploads_extraction_status", "extraction_status", "created_at_utc"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"))
    filing_period_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("filing_periods.id", ondelete="CASCADE"))
    uploaded_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))

    original_file_name: Mapped[str] = mapped_column(String(260))
    content_type: Mapped[str] = mapped_column(String(120))
    source_file_kind: Mapped[str] = mapped_column(String(20))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str | None] = mapped_column(String(64))

    storage_provider: Mapped[str] = mapped_column(String(40))
    storage_container: Mapped[str] = mapped_column(String(80))
    storage_path: Mapped[str] = mapped_column(String(500))
    created_at_utc: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    extraction_status: Mapped[str] = mapped_column(String(20), default=ExtractionStatus.PENDING.value)
    extraction_error: Mapped[str | None] = mapped_column(String(2000))
    extraction_started_at_utc: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    extraction_completed_at_utc: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    documents: Mapped[list[DteDocument]] = relationship(
        back_populates="upload", cascade="all, delete-orphan", passive_deletes=True
    )


class DteDocument(Base):
    """One DTE read from an upload, editable in the review table before generating anexos."""

    __tablename__ = "dte_documents"
    __table_args__ = (
        Index("ix_dte_documents_period", "filing_period_id", "fecha_emision"),
        Index("ix_dte_documents_codigo", "filing_period_id", "codigo_generacion"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    upload_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("uploads.id", ondelete="CASCADE"), index=True)
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"))
    filing_period_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("filing_periods.id", ondelete="CASCADE"))

    extraction_method: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default=DocumentStatus.OK.value)
    issues: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    # Exactly what extraction produced, kept for audit after user edits.
    extracted: Mapped[dict] = mapped_column(JSONB, default=dict)
    # Issues reported by the extractor itself (e.g. AI fallback used). Shown until the user edits.
    extraction_issues: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    edited: Mapped[bool] = mapped_column(Boolean, default=False)
    excluded: Mapped[bool] = mapped_column(Boolean, default=False)

    tipo_dte: Mapped[str] = mapped_column(String(2))
    codigo_generacion: Mapped[str | None] = mapped_column(String(64))
    numero_control: Mapped[str | None] = mapped_column(String(64))
    sello_recepcion: Mapped[str | None] = mapped_column(String(64))
    fecha_emision: Mapped[dt.date | None] = mapped_column(Date)
    hora_emision: Mapped[dt.time | None] = mapped_column(Time)

    emisor_nombre: Mapped[str | None] = mapped_column(String(250))
    emisor_nit: Mapped[str | None] = mapped_column(String(20))
    emisor_nrc: Mapped[str | None] = mapped_column(String(20))

    receptor_nombre: Mapped[str | None] = mapped_column(String(250))
    receptor_nit: Mapped[str | None] = mapped_column(String(20))
    receptor_nrc: Mapped[str | None] = mapped_column(String(20))
    receptor_dui: Mapped[str | None] = mapped_column(String(20))

    total_no_sujetas: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"))
    total_exentas: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"))
    total_gravadas: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"))
    iva: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"))
    iva_retenido: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"))
    total: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"))

    # Per-document overrides; null means "use the client default".
    tipo_operacion_renta: Mapped[str | None] = mapped_column(String(2))
    tipo_ingreso_renta: Mapped[str | None] = mapped_column(String(2))

    created_at_utc: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at_utc: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    upload: Mapped[Upload] = relationship(back_populates="documents")


class GenerationRun(Base):
    __tablename__ = "generation_runs"
    __table_args__ = (
        UniqueConstraint("filing_period_id", "version", name="uq_generation_runs_period_version"),
        Index(
            "ix_generation_runs_active_per_period",
            "filing_period_id",
            unique=True,
            postgresql_where=text("status IN ('Pending', 'Running')"),
        ),
        Index("ix_generation_runs_status_created", "status", "created_at_utc"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"))
    filing_period_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("filing_periods.id", ondelete="CASCADE"))
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default=RunStatus.PENDING.value)
    error_message: Mapped[str | None] = mapped_column(String(2000))
    # Non-blocking issues reported by the anexo builder for this run.
    issues: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    created_at_utc: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at_utc: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at_utc: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    files: Mapped[list[GenerationRunFile]] = relationship(
        back_populates="run", cascade="all, delete-orphan", passive_deletes=True
    )
    artifacts: Mapped[list[OutputArtifact]] = relationship(
        back_populates="run", cascade="all, delete-orphan", passive_deletes=True
    )


class GenerationRunFile(Base):
    __tablename__ = "generation_run_files"
    __table_args__ = (UniqueConstraint("generation_run_id", "upload_id", name="uq_run_files_run_upload"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    generation_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("generation_runs.id", ondelete="CASCADE"))
    upload_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("uploads.id", ondelete="SET NULL"))
    original_file_name: Mapped[str] = mapped_column(String(260))
    source_file_kind: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default=RunFileStatus.PENDING.value)
    error_message: Mapped[str | None] = mapped_column(String(2000))

    run: Mapped[GenerationRun] = relationship(back_populates="files")


class OutputArtifact(Base):
    __tablename__ = "output_artifacts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    generation_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("generation_runs.id", ondelete="CASCADE"))
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"))
    filing_period_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("filing_periods.id", ondelete="CASCADE"))
    artifact_kind: Mapped[str] = mapped_column(String(20), default="CSV")
    file_name: Mapped[str] = mapped_column(String(260))
    content_type: Mapped[str] = mapped_column(String(120), default="text/csv")
    size_bytes: Mapped[int] = mapped_column(Integer)
    row_count: Mapped[int | None] = mapped_column(Integer)
    storage_provider: Mapped[str] = mapped_column(String(40))
    storage_container: Mapped[str] = mapped_column(String(80))
    storage_path: Mapped[str] = mapped_column(String(500))
    created_at_utc: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    run: Mapped[GenerationRun] = relationship(back_populates="artifacts")
