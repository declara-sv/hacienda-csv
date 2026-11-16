"""Versioned Claude API price table used to estimate the cost of each AI call.

Prices are USD per million tokens. Check them against Anthropic's pricing page
(https://www.anthropic.com/pricing) whenever they are updated, and bump `PRICE_VERSION` with every
change. Each usage event stores its raw token counts next to the `price_version` used, so the raw
tokens are the source of truth: costs can always be recalculated with a corrected table.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

PRICE_VERSION = "2026-11"

_MILLION = Decimal(1_000_000)
_COST_QUANTUM = Decimal("0.000001")


@dataclass(frozen=True)
class ModelPrice:
    input: Decimal
    output: Decimal
    cache_read: Decimal
    cache_write: Decimal


PRICES: dict[str, ModelPrice] = {
    "claude-opus-5-5": ModelPrice(Decimal("4.00"), Decimal("20.00"), Decimal("0.20"), Decimal("5.00")),
    "claude-sonnet-5-5": ModelPrice(Decimal("2.00"), Decimal("10.00"), Decimal("0.10"), Decimal("2.50")),
    "claude-haiku-5-5": ModelPrice(Decimal("0.10"), Decimal("0.50"), Decimal("0.01"), Decimal("0.125")),
}


def price_for(model: str | None) -> ModelPrice | None:
    if not model:
        return None
    return PRICES.get(model.strip().lower())


def cost_usd(
    model: str | None,
    *,
    input_tokens: int | None,
    output_tokens: int | None,
    cache_read_tokens: int | None = None,
    cache_creation_tokens: int | None = None,
) -> Decimal | None:
    """Cost of one call, rounded to 6 decimals. None for an unknown model or a call without tokens."""
    price = price_for(model)
    tokens = (input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens)
    if price is None or all(t is None for t in tokens):
        return None
    total = (
        Decimal(input_tokens or 0) * price.input
        + Decimal(output_tokens or 0) * price.output
        + Decimal(cache_read_tokens or 0) * price.cache_read
        + Decimal(cache_creation_tokens or 0) * price.cache_write
    )
    return (total / _MILLION).quantize(_COST_QUANTUM)
