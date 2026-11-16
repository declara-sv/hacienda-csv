from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUserId
from app.services import integrations

router = APIRouter(prefix="/api/catalogs", tags=["catalogs"])


@router.get("/renta")
def renta_catalog(user_id: CurrentUserId) -> dict:
    """Códigos de Renta (F-07 desde 01/2025): `{"tipoOperacion": [...], "tipoIngreso": [...]}`."""
    return integrations.renta_catalog() or {"tipoOperacion": [], "tipoIngreso": []}
