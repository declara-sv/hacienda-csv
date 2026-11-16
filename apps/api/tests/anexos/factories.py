"""Synthetic DTE data for anexo tests (no real taxpayers)."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from app.domain import ClientProfile, DteRecord, ReviewedDocument

CLIENT = ClientProfile(
    nit="06140101001010", nrc="1234567", default_tipo_operacion="1", default_tipo_ingreso="3"
)


def code(n: int, prefix: str = "AAAAAAAA") -> str:
    return f"{prefix}-1111-4222-8333-{n:012d}"


def factura(
    n: int,
    day: int,
    *,
    hora: dt.time | None = dt.time(9, 0),
    exentas: str = "0.00",
    no_sujetas: str = "0.00",
    gravadas: str = "0.00",
    month: int = 10,
    year: int = 2026,
    doc_id: str | None = None,
    **overrides: Any,
) -> ReviewedDocument:
    renta = {k: overrides.pop(k) for k in ("tipo_operacion_renta", "tipo_ingreso_renta") if k in overrides}
    total = Decimal(exentas) + Decimal(no_sujetas) + Decimal(gravadas)
    record = DteRecord(
        tipo_dte="01",
        codigo_generacion=code(n),
        numero_control=f"DTE-01-M001P001-{n:015d}",
        sello_recepcion=f"2026SELLOFAC{n:028d}",
        fecha_emision=dt.date(year, month, day),
        hora_emision=hora,
        receptor_nombre="Consumidor final",
        total_exentas=Decimal(exentas),
        total_no_sujetas=Decimal(no_sujetas),
        total_gravadas=Decimal(gravadas),
        total=total,
        **overrides,
    )
    return ReviewedDocument(id=doc_id or f"fac-{n}", record=record, **renta)


def ccf(
    n: int,
    day: int,
    *,
    tipo: str = "03",
    gravadas: str = "100.00",
    iva: str | None = None,
    exentas: str = "0.00",
    no_sujetas: str = "0.00",
    nit: str | None = "0614-010190-101-3",
    dui: str | None = None,
    nrc: str | None = "123456-7",
    nombre: str = "Empresa Ficticia, S.A. de C.V.",
    hora: dt.time | None = dt.time(10, 0),
    month: int = 10,
    year: int = 2026,
    **overrides: Any,
) -> ReviewedDocument:
    renta = {k: overrides.pop(k) for k in ("tipo_operacion_renta", "tipo_ingreso_renta") if k in overrides}
    grav = Decimal(gravadas)
    iva_amount = Decimal(iva) if iva is not None else (grav * Decimal("0.13")).quantize(Decimal("0.01"))
    record = DteRecord(
        tipo_dte=tipo,
        codigo_generacion=code(n, "CCCCCCCC"),
        numero_control=f"DTE-{tipo}-M001P001-{n:015d}",
        sello_recepcion=f"2026A1B2C3D4E5F6A7B8C9D0E1F2A3B4{n:08d}",
        fecha_emision=dt.date(year, month, day),
        hora_emision=hora,
        receptor_nombre=nombre,
        receptor_nit=nit,
        receptor_dui=dui,
        receptor_nrc=nrc,
        total_exentas=Decimal(exentas),
        total_no_sujetas=Decimal(no_sujetas),
        total_gravadas=grav,
        iva=iva_amount,
        total=Decimal(exentas) + Decimal(no_sujetas) + grav + iva_amount,
        **overrides,
    )
    return ReviewedDocument(id=f"ccf-{n}", record=record, **renta)


def lines(content: bytes) -> list[str]:
    text = content.decode("windows-1252")
    assert text.endswith("\r\n")
    return text[:-2].split("\r\n")
