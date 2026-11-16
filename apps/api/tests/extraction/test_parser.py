import datetime as dt
from decimal import Decimal

import pytest

from app.domain import ExtractionMethod
from app.extraction import extract_pdf
from app.extraction.layout import Page, Word, group_lines
from app.extraction.mh_parser import parse_pages

from .support import FakeAi, build_pdf, drop_words, load_pages, replace_word


def _set_amount(page: Page, label: str, value: str) -> Page:
    """Replace the amount printed at the end of the line starting with `label`."""
    for line in group_lines(page.words):
        if line.text.startswith(label):
            target = line.words[-1]
            words = [Word(value, w.x0, w.x1, w.top, w.bottom) if w is target else w for w in page.words]
            return Page(page.width, page.height, words)
    raise AssertionError(f"label not found: {label}")


def _single(pages: list[Page]):
    outcome = parse_pages(pages)
    assert outcome.failure is None
    assert len(outcome.documents) == 1
    return outcome.documents[0]


def test_factura_with_exentas_and_gravadas():
    doc = _single(load_pages("factura_exentas_gravadas.json"))
    r = doc.record
    assert doc.issues == []
    assert r.tipo_dte == "01"
    assert r.codigo_generacion == "0A1B2C3D-4E5F-4A6B-8C7D-9E0F1A2B3C4D"
    assert r.numero_control == "DTE-01-M001P001-000000000000101"
    assert r.sello_recepcion == "2026ABCDEF0123456789ABCDEF0123456789ABCD"
    assert r.fecha_emision == dt.date(2026, 10, 5)
    assert r.hora_emision == dt.time(10, 15, 30)
    assert r.emisor_nombre == "FARMACIA DEMO DE PRUEBAS SV"
    assert r.emisor_nit == "01234567-8"
    assert r.emisor_nrc == "1234-5"
    assert (r.receptor_nombre, r.receptor_nit, r.receptor_nrc, r.receptor_dui) == (None, None, None, None)
    assert (r.total_no_sujetas, r.total_exentas, r.total_gravadas) == (
        Decimal("0.00"),
        Decimal("2.50"),
        Decimal("48.14"),
    )
    assert r.iva == Decimal("0.00")
    assert r.iva_retenido == Decimal("0.00")
    assert r.total == Decimal("50.64")


def test_factura_only_gravadas():
    r = _single(load_pages("factura_gravadas.json")).record
    assert r.tipo_dte == "01"
    assert (r.total_no_sujetas, r.total_exentas, r.total_gravadas, r.total) == (
        Decimal("0.00"),
        Decimal("0.00"),
        Decimal("54.30"),
        Decimal("54.30"),
    )
    assert r.hora_emision == dt.time(11, 20)


def test_synthetic_ccf_reads_receptor_and_iva():
    doc = _single(load_pages("ccf_synthetic.json"))
    r = doc.record
    assert doc.issues == []
    assert r.tipo_dte == "03"
    assert r.numero_control == "DTE-03-M001P001-000000000000055"
    assert r.receptor_nombre == "CLIENTE DEMO, S.A. DE C.V."
    assert r.receptor_nit == "0614-010101-101-1"
    assert r.receptor_nrc == "123456-7"
    assert r.total_gravadas == Decimal("100.00")
    assert r.iva == Decimal("13.00")
    assert r.total == Decimal("113.00")


def test_receptor_dui_under_unlabelled_id():
    page = load_pages("factura_gravadas.json")[0]
    # The receptor's identification line prints "- -" (label and value) when empty; fill the value.
    receptor_dash = [w for w in page.words if w.text == "-" and 160 < w.top < 172 and w.x0 > 396]
    assert len(receptor_dash) == 1
    words = [
        Word("04567890-1", w.x0, w.x0 + 37, w.top, w.bottom) if w is receptor_dash[0] else w
        for w in page.words
    ]
    r = _single([Page(page.width, page.height, words)]).record
    assert r.receptor_dui == "04567890-1"
    assert r.receptor_nit is None


def test_title_and_control_prefix_must_agree():
    page = replace_word(load_pages("factura_gravadas.json")[0], "FACTURA", "NOTA")
    page = Page(page.width, page.height, page.words + [Word("DE", 330, 340, 63.49, 70.49)])
    page = Page(page.width, page.height, page.words + [Word("CRÉDITO", 343, 375, 63.49, 70.49)])
    doc = _single([page])
    assert doc.record.tipo_dte == "05"
    assert "tipo_dte_mismatch" in [i.code for i in doc.issues]


def test_missing_totals_are_errors_not_zeros():
    page = drop_words(load_pages("factura_gravadas.json")[0], lambda w: 535 < w.top < 670)
    doc = _single([page])
    codes = {(i.code, i.field) for i in doc.issues}
    assert ("amount_not_found", "total_gravadas") in codes
    assert ("amount_not_found", "total") in codes


def test_global_discounts_are_subtracted():
    page = load_pages("factura_gravadas.json")[0]
    page = _set_amount(page, "Descuento global a ventas gravadas", "4.30")
    page = _set_amount(page, "Monto Total de la Operación", "50.00")
    r = _single([page]).record
    assert r.total_gravadas == Decimal("50.00")
    assert r.total == Decimal("50.00")


def test_amounts_with_thousands_separator():
    page = load_pages("factura_gravadas.json")[0]
    words = [
        Word("1,054.30", w.x0 - 10, w.x1, w.top, w.bottom) if w.text == "54.30" else w for w in page.words
    ]
    r = _single([Page(page.width, page.height, words)]).record
    assert r.total_gravadas == Decimal("1054.30")
    assert r.total == Decimal("1054.30")


def test_two_dtes_in_one_pdf_give_two_records():
    first = load_pages("factura_exentas_gravadas.json")[0]
    second = load_pages("factura_gravadas.json")[0]
    outcome = parse_pages([first, second])
    assert [d.record.codigo_generacion for d in outcome.documents] == [
        "0A1B2C3D-4E5F-4A6B-8C7D-9E0F1A2B3C4D",
        "5E6F7A8B-9C0D-4E1F-A2B3-C4D5E6F7A8B9",
    ]
    assert [d.record.total for d in outcome.documents] == [Decimal("50.64"), Decimal("54.30")]


def test_repeated_header_with_same_code_continues_the_document():
    full = load_pages("factura_gravadas.json")[0]
    first = drop_words(full, lambda w: w.top > 535)  # items continue on the next page, totals at the end
    outcome = parse_pages([first, full])
    assert len(outcome.documents) == 1
    assert outcome.documents[0].record.total == Decimal("54.30")
    assert outcome.documents[0].issues == []


def test_continuation_page_without_header():
    full = load_pages("factura_gravadas.json")[0]
    first = drop_words(full, lambda w: w.top > 535)
    last = drop_words(full, lambda w: w.top <= 535)
    outcome = parse_pages([first, last])
    assert len(outcome.documents) == 1
    assert outcome.documents[0].record.total == Decimal("54.30")


def test_unknown_template():
    page = Page(612, 792, [Word("RECIBO", 50, 90, 50, 57), Word("123", 95, 110, 50, 57)])
    outcome = parse_pages([page])
    assert outcome.documents == []
    assert outcome.failure_code == "template_not_recognized"


def test_page_without_text():
    outcome = parse_pages([Page(612, 792, [])])
    assert outcome.documents == []
    assert outcome.failure_code == "pdf_has_no_text"


@pytest.mark.parametrize(
    ("fixture", "tipo", "total"),
    [
        ("factura_exentas_gravadas.json", "01", Decimal("50.64")),
        ("factura_gravadas.json", "01", Decimal("54.30")),
        ("ccf_synthetic.json", "03", Decimal("113.00")),
    ],
)
def test_end_to_end_through_a_real_pdf(fixture, tipo, total):
    result = extract_pdf(build_pdf(load_pages(fixture)), ai=None)
    assert result.method == ExtractionMethod.PARSER
    assert result.issues == []
    assert [(r.tipo_dte, r.total) for r in result.records] == [(tipo, total)]
    assert result.raw_text and "DOCUMENTO TRIBUTARIO ELECTRÓNICO" in result.raw_text


def test_missing_sello_on_a_factura_is_only_a_warning():
    page = drop_words(load_pages("factura_gravadas.json")[0], lambda w: w.text.startswith("2026FEDCBA"))
    ai = FakeAi()
    result = extract_pdf(build_pdf([page]), ai=ai)
    assert ai.calls == 0
    assert result.records[0].sello_recepcion is None
    assert result.records[0].fecha_emision == dt.date(2026, 10, 6)
    assert [(i.code, i.severity) for i in result.issues] == [("missing_sello_recepcion", "Warning")]
