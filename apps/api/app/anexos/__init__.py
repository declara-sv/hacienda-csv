"""F-07 sales anexos: spec-as-data, Renta catalog, validation, and CSV generation."""

from app.anexos.builder import build_sales_anexos
from app.anexos.catalog import RENTA_CATALOG
from app.anexos.rules import anexo_for_tipo, effective_renta_codes
from app.anexos.validation import validate_for_anexo

__all__ = [
    "RENTA_CATALOG",
    "anexo_for_tipo",
    "build_sales_anexos",
    "effective_renta_codes",
    "validate_for_anexo",
]
