"""Renta catalogs (tipo de operación / tipo de ingreso) for F-07 columns R/S (Anexo 1) and U/V (Anexo 2)."""

from __future__ import annotations

import json
from importlib import resources
from typing import Any

from pydantic import BaseModel, field_validator

CATALOG_FILE = "renta_v2025.json"

# From this period on the Renta codes are mandatory; earlier periods report "0".
RENTA_REQUIRED_FROM = (2025, 1)
RENTA_VALUE_BEFORE_REQUIRED = "0"


class CatalogEntry(BaseModel):
    code: str
    label: str

    @field_validator("code")
    @classmethod
    def _digits(cls, value: str) -> str:
        if not value.isdigit():
            raise ValueError(f"el código {value!r} debe ser numérico")
        return value


class RentaCatalog(BaseModel):
    tipoOperacion: list[CatalogEntry]  # noqa: N815 - matches the JSON/API shape
    tipoIngreso: list[CatalogEntry]  # noqa: N815


def _load() -> dict[str, Any]:
    text = resources.files("app.anexos").joinpath("catalogs", CATALOG_FILE).read_text(encoding="utf-8")
    catalog = RentaCatalog.model_validate(json.loads(text))
    return catalog.model_dump()


RENTA_CATALOG: dict[str, list[dict[str, str]]] = _load()

TIPO_OPERACION_CODES = frozenset(e["code"] for e in RENTA_CATALOG["tipoOperacion"])
TIPO_INGRESO_CODES = frozenset(e["code"] for e in RENTA_CATALOG["tipoIngreso"])


def renta_required(year: int, month: int) -> bool:
    return (year, month) >= RENTA_REQUIRED_FROM
