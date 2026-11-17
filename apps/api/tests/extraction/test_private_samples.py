"""Exact-value checks over the real MH samples. The files are gitignored; tests skip without them.

Identifiers that could locate the real documents (código de generación, número de control, sello)
are compared by SHA-256 so their printed values stay out of the repository.
"""

import datetime as dt
import hashlib
import re
from decimal import Decimal

import pytest

from app.domain import ExtractionMethod
from app.extraction import extract_pdf, validate_record

from .support import PRIVATE_FIXTURES, FakeAi

CASES = [
    (
        "factura_exentas_gravadas.pdf",
        {
            "codigo_generacion": "bd7aab07299216dd1b9e4770ac5b64c46b2627c9f7364d99bd0d2aad081799f2",
            "numero_control": "ee8ce291fb4b26e9ec4298b90e0f1b4639f0c3c4456c374f49fec06c4fc32b2c",
            "sello_recepcion": "f45a3a0e6a787e7e2fe1dc8853f48291effc7a1c7969502aa7c48fff353dc4ea",
            "fecha_emision": dt.date(2026, 10, 1),
            "hora_emision": dt.time(9, 18, 52),
            "amounts": ("0.00", "2.50", "48.14", "50.64"),
        },
    ),
    (
        "factura_gravadas.pdf",
        {
            "codigo_generacion": "052664cb0701582c22a53529065f12608123f0e042e6e2fbcccc8b36cb4405c2",
            "numero_control": "e86ebcdd51b0fb811a37f154ce31b3b1b52acd5caa3413d18b740a27cba9912b",
            "sello_recepcion": "c3fbf6a90e43641e3f722e44e46346bbf3030a33f99ad14d1461e527ad1cd814",
            "fecha_emision": dt.date(2026, 10, 2),
            "hora_emision": dt.time(9, 29, 45),
            "amounts": ("0.00", "0.00", "54.30", "54.30"),
        },
    ),
]


def _sha256(value: str | None) -> str:
    return hashlib.sha256((value or "").encode()).hexdigest()


@pytest.mark.parametrize(("file_name", "expected"), CASES, ids=[c[0] for c in CASES])
def test_private_sample(file_name, expected):
    path = PRIVATE_FIXTURES / file_name
    if not path.exists():
        pytest.skip(f"private sample {file_name} not present")

    ai = FakeAi()
    result = extract_pdf(path.read_bytes(), ai=ai)
    assert ai.calls == 0
    assert result.method == ExtractionMethod.PARSER
    assert result.issues == []
    (record,) = result.records

    assert record.tipo_dte == "01"
    for name in ("codigo_generacion", "numero_control", "sello_recepcion"):
        assert _sha256(getattr(record, name)) == expected[name], name
    assert re.fullmatch(
        r"[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}", record.codigo_generacion
    )
    assert re.fullmatch(r"DTE-01-[A-Z0-9]{8}-\d{15}", record.numero_control)
    assert record.fecha_emision == expected["fecha_emision"]
    assert record.hora_emision == expected["hora_emision"]
    no_sujetas, exentas, gravadas, total = (Decimal(a) for a in expected["amounts"])
    assert record.total_no_sujetas == no_sujetas
    assert record.total_exentas == exentas
    assert record.total_gravadas == gravadas
    assert record.iva == Decimal("0.00")
    assert record.iva_retenido == Decimal("0.00")
    assert record.total == total

    # Emisor identifiers keep their dashes; the factura has no receptor.
    assert record.emisor_nombre
    assert record.emisor_nit and re.fullmatch(r"\d+-\d", record.emisor_nit)
    assert record.emisor_nrc and re.fullmatch(r"\d+-\d", record.emisor_nrc)
    assert (record.receptor_nombre, record.receptor_nit, record.receptor_nrc, record.receptor_dui) == (
        None,
        None,
        None,
        None,
    )
    assert validate_record(record) == []
