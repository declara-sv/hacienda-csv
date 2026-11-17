"""Typed helpers that append rows to the usage ledger.

Events are added to the caller's session so they commit (or roll back) with the business change they
describe. Each insert runs inside a SAVEPOINT: if the insert itself fails, it is logged and skipped,
and the business operation continues. Pending business changes are flushed before the savepoint, so
their own errors still propagate to the caller.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, replace
from typing import Any

from sqlalchemy.orm import Session

from app.domain import AiUsage
from app.models import Client, UsageEvent, UsageEventType
from app.usage import pricing

logger = logging.getLogger(__name__)

MAX_ERROR_LENGTH = 2000


@dataclass(frozen=True)
class UsageScope:
    """Who and what an event is about. Ids are copied as plain values (no foreign keys)."""

    account_id: uuid.UUID
    actor_user_id: uuid.UUID | None = None
    client_id: uuid.UUID | None = None
    client_name: str | None = None
    filing_period_id: uuid.UUID | None = None
    upload_id: uuid.UUID | None = None
    run_id: uuid.UUID | None = None
    artifact_id: uuid.UUID | None = None

    @classmethod
    def for_client(cls, client: Client, actor_user_id: uuid.UUID | None, **ids: Any) -> UsageScope:
        return cls(
            account_id=client.account_id,
            actor_user_id=actor_user_id,
            client_id=client.id,
            client_name=client.name,
            **ids,
        )

    def with_ids(self, **ids: Any) -> UsageScope:
        return replace(self, **ids)


def record(session: Session, event_type: UsageEventType, scope: UsageScope, **fields: Any) -> None:
    """Append one event. Never raises because of the event insert itself."""
    metadata = fields.pop("metadata", None) or {}
    event = UsageEvent(
        event_type=event_type.value,
        account_id=scope.account_id,
        actor_user_id=scope.actor_user_id,
        client_id=scope.client_id,
        client_name=scope.client_name,
        filing_period_id=scope.filing_period_id,
        upload_id=scope.upload_id,
        run_id=scope.run_id,
        artifact_id=scope.artifact_id,
        metadata_=metadata,
        **fields,
    )
    session.flush()  # pending business changes first, outside the guard: their errors must propagate
    try:
        with session.begin_nested():
            session.add(event)
    except Exception:
        logger.exception("No se pudo registrar el evento de uso %s.", event_type.value)


def upload_stored(session: Session, scope: UsageScope, *, size_bytes: int, source_file_kind: str) -> None:
    record(
        session,
        UsageEventType.UPLOAD_STORED,
        scope,
        bytes=size_bytes,
        metadata={"sourceFileKind": source_file_kind},
    )


def extraction_completed(
    session: Session,
    scope: UsageScope,
    *,
    method: str,
    pages: int | None,
    documents: int,
    duration_ms: int | None,
) -> None:
    record(
        session,
        UsageEventType.EXTRACTION_COMPLETED,
        scope,
        extraction_method=method,
        pages=pages,
        documents=documents,
        duration_ms=duration_ms,
    )


def extraction_failed(
    session: Session,
    scope: UsageScope,
    *,
    error: str,
    method: str | None,
    pages: int | None,
    duration_ms: int | None,
) -> None:
    record(
        session,
        UsageEventType.EXTRACTION_FAILED,
        scope,
        extraction_method=method,
        pages=pages,
        documents=0,
        duration_ms=duration_ms,
        metadata={"error": error[:MAX_ERROR_LENGTH]},
    )


def ai_calls(
    session: Session, scope: UsageScope, calls: list[AiUsage], *, extra: dict[str, Any] | None = None
) -> None:
    """One `ai_call` event per Claude API call, priced with the current price table."""
    for call in calls:
        cost = pricing.cost_usd(
            call.model,
            input_tokens=call.input_tokens,
            output_tokens=call.output_tokens,
            cache_read_tokens=call.cache_read_tokens,
            cache_creation_tokens=call.cache_creation_tokens,
        )
        record(
            session,
            UsageEventType.AI_CALL,
            scope,
            ai_model=call.model,
            ai_input_tokens=call.input_tokens,
            ai_output_tokens=call.output_tokens,
            ai_cache_read_tokens=call.cache_read_tokens,
            ai_cache_creation_tokens=call.cache_creation_tokens,
            cost_usd=cost,
            price_version=pricing.PRICE_VERSION if cost is not None else None,
            duration_ms=call.duration_ms,
            metadata={"outcome": call.outcome.value, **(extra or {})},
        )


def run_completed(
    session: Session,
    scope: UsageScope,
    *,
    documents: int,
    rows: int,
    files: int,
    size_bytes: int,
    version: int,
) -> None:
    record(
        session,
        UsageEventType.RUN_COMPLETED,
        scope,
        documents=documents,
        rows=rows,
        bytes=size_bytes,
        metadata={"files": files, "version": version},
    )


def artifact_downloaded(session: Session, scope: UsageScope, *, size_bytes: int, file_name: str) -> None:
    record(
        session,
        UsageEventType.ARTIFACT_DOWNLOADED,
        scope,
        bytes=size_bytes,
        metadata={"fileName": file_name},
    )
