"""Helpers for extraction tests: fixture loading, a tiny PDF writer and a fake AI extractor."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.domain import DteRecord
from app.extraction.layout import Page, Word

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
EXTRACTION_FIXTURES = FIXTURES / "extraction"
PRIVATE_FIXTURES = FIXTURES / "private"


def load_pages(name: str) -> list[Page]:
    data = json.loads((EXTRACTION_FIXTURES / name).read_text(encoding="utf-8"))
    return [
        Page(
            width=page["width"],
            height=page["height"],
            words=[Word(text, x0, x1, top, bottom) for text, x0, x1, top, bottom in page["words"]],
        )
        for page in data["pages"]
    ]


def replace_word(page: Page, old: str, new: str) -> Page:
    return Page(
        page.width,
        page.height,
        [Word(new, w.x0, w.x1, w.top, w.bottom) if w.text == old else w for w in page.words],
    )


def drop_words(page: Page, predicate: Any) -> Page:
    return Page(page.width, page.height, [w for w in page.words if not predicate(w)])


def _pdf_string(text: str) -> bytes:
    raw = text.encode("cp1252", errors="replace")
    return b"(" + raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)") + b")"


def build_pdf(pages: list[Page]) -> bytes:
    """Minimal PDF with each word drawn in Helvetica at its coordinates (no text when a page has no words).

    Good enough for pdfplumber to return the same words, so tests can exercise the real PDF path
    without committing real documents.
    """
    objects: list[bytes] = []

    def add(obj: bytes) -> int:
        objects.append(obj)
        return len(objects)

    font_id = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    pages_id = add(b"")  # placeholder, filled once the kids are known
    kids: list[int] = []
    for page in pages:
        ops: list[bytes] = []
        for w in page.words:
            size = max(w.bottom - w.top, 1.0)
            baseline = page.height - w.bottom + 0.21 * size
            ops.append(
                b"BT /F1 %.2f Tf %.2f %.2f Td %s Tj ET" % (size, w.x0, baseline, _pdf_string(w.text + " "))
            )
        stream = b"\n".join(ops)
        content_id = add(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream))
        kids.append(
            add(
                b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %.2f %.2f]"
                b" /Resources << /Font << /F1 %d 0 R >> >> /Contents %d 0 R >>"
                % (pages_id, page.width, page.height, font_id, content_id)
            )
        )
    objects[pages_id - 1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (
        b" ".join(b"%d 0 R" % k for k in kids),
        len(kids),
    )
    catalog_id = add(b"<< /Type /Catalog /Pages %d 0 R >>" % pages_id)

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (number, obj)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        catalog_id,
        xref,
    )
    return bytes(out)


def make_record(**overrides: Any) -> DteRecord:
    """A valid Factura (01) record; override fields per test."""
    data: dict[str, Any] = {
        "tipo_dte": "01",
        "codigo_generacion": "0A1B2C3D-4E5F-4A6B-8C7D-9E0F1A2B3C4D",
        "numero_control": "DTE-01-M001P001-000000000000101",
        "sello_recepcion": "2026ABCDEF0123456789ABCDEF0123456789ABCD",
        "fecha_emision": "2026-10-05",
        "hora_emision": "10:15:30",
        "emisor_nombre": "FARMACIA DEMO DE PRUEBAS SV",
        "emisor_nit": "01234567-8",
        "emisor_nrc": "1234-5",
        "total_no_sujetas": Decimal("0.00"),
        "total_exentas": Decimal("2.50"),
        "total_gravadas": Decimal("48.14"),
        "iva": Decimal("0.00"),
        "iva_retenido": Decimal("0.00"),
        "total": Decimal("50.64"),
    }
    data.update(overrides)
    return DteRecord.model_validate(data)


def make_ccf(**overrides: Any) -> DteRecord:
    data: dict[str, Any] = {
        "tipo_dte": "03",
        "codigo_generacion": "7B8C9D0E-1F2A-4B3C-9D4E-5F6A7B8C9D0E",
        "numero_control": "DTE-03-M001P001-000000000000055",
        "receptor_nombre": "CLIENTE DEMO, S.A. DE C.V.",
        "receptor_nit": "0614-010101-101-1",
        "receptor_nrc": "123456-7",
        "total_exentas": Decimal("0.00"),
        "total_gravadas": Decimal("100.00"),
        "iva": Decimal("13.00"),
        "total": Decimal("113.00"),
    }
    data.update(overrides)
    return make_record(**data)


class FakeAi:
    """AiExtractor double: returns fixed records or raises."""

    def __init__(self, records: list[DteRecord] | None = None, error: Exception | None = None) -> None:
        self.records = records or []
        self.error = error
        self.calls = 0

    def extract(self, pdf_bytes: bytes) -> list[DteRecord]:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return list(self.records)
