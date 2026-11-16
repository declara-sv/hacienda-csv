"""Monthly usage report of the current account, read from the `usage_monthly` view."""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Query
from sqlalchemy import text

from app.api.deps import CurrentAccount, DbSession
from app.api.schemas import UsageReportDto, UsageTotalsDto
from app.domain import ExtractionMethod
from app.models import UsageEventType

router = APIRouter(prefix="/api/usage", tags=["usage"])

_MONTHLY_SQL = text(
    """
    SELECT client_id, client_name, event_type, extraction_method, events, bytes, documents, rows,
           ai_input_tokens, ai_output_tokens, ai_cache_read_tokens, ai_cache_creation_tokens,
           cost_usd, unpriced_ai_calls
    FROM usage_monthly
    WHERE account_id = :account_id AND month = :month
    """
)

_COST_QUANTUM = Decimal("0.000001")
_METHOD_FIELDS = {
    ExtractionMethod.PARSER.value: "parser",
    ExtractionMethod.AI.value: "ai",
    ExtractionMethod.MANUAL.value: "manual",
}


class _Totals:
    def __init__(self, client_id: uuid.UUID | None = None, client_name: str | None = None) -> None:
        self.dto = UsageTotalsDto(client_id=client_id, client_name=client_name)
        self.cost = Decimal(0)

    def add(self, row: Any) -> None:
        dto = self.dto
        events = int(row.events or 0)
        event_type = row.event_type
        if event_type == UsageEventType.UPLOAD_STORED:
            dto.uploads += events
            dto.bytes_stored += int(row.bytes or 0)
        elif event_type == UsageEventType.EXTRACTION_COMPLETED:
            documents = int(row.documents or 0)
            field = _METHOD_FIELDS.get(row.extraction_method or "")
            if field is not None:
                setattr(dto.documents_extracted, field, getattr(dto.documents_extracted, field) + documents)
            dto.documents_extracted.total += documents
        elif event_type == UsageEventType.EXTRACTION_FAILED:
            dto.extractions_failed += events
        elif event_type == UsageEventType.AI_CALL:
            dto.ai_calls += events
            dto.ai_input_tokens += int(row.ai_input_tokens or 0)
            dto.ai_output_tokens += int(row.ai_output_tokens or 0)
            dto.ai_cache_read_tokens += int(row.ai_cache_read_tokens or 0)
            dto.ai_cache_creation_tokens += int(row.ai_cache_creation_tokens or 0)
            dto.ai_calls_unpriced += int(row.unpriced_ai_calls or 0)
            self.cost += Decimal(row.cost_usd or 0)
        elif event_type == UsageEventType.RUN_COMPLETED:
            dto.runs += events
            dto.rows_generated += int(row.rows or 0)
        elif event_type == UsageEventType.ARTIFACT_DOWNLOADED:
            dto.downloads += events

    def result(self) -> UsageTotalsDto:
        self.dto.ai_cost_usd = str(self.cost.quantize(_COST_QUANTUM))
        return self.dto


@router.get("")
def monthly_usage(
    session: DbSession,
    account: CurrentAccount,
    year: Annotated[int, Query(ge=2000, le=2100)],
    month: Annotated[int, Query(ge=1, le=12)],
) -> UsageReportDto:
    """Per-client totals of the current account for one month (UTC), plus the account total."""
    rows = session.execute(_MONTHLY_SQL, {"account_id": account.account_id, "month": dt.date(year, month, 1)})
    total = _Totals()
    by_client: dict[uuid.UUID | None, _Totals] = {}
    for row in rows:
        totals = by_client.get(row.client_id)
        if totals is None:
            totals = by_client[row.client_id] = _Totals(row.client_id, row.client_name)
        totals.add(row)
        total.add(row)

    clients = sorted(
        (t.result() for t in by_client.values()),
        key=lambda c: ((c.client_name or "").lower(), str(c.client_id)),
    )
    return UsageReportDto(year=year, month=month, clients=clients, total=total.result())
