from decimal import Decimal

from app.domain import ExtractionMethod, IssueSeverity
from app.extraction import AiExtractionError, extract_pdf
from app.extraction.layout import Page

from .support import FakeAi, build_pdf, drop_words, load_pages, make_record


def _codes(result):
    return [(i.code, i.severity) for i in result.issues]


def _pdf(name="factura_gravadas.json"):
    return build_pdf(load_pages(name))


def _pdf_without_totals():
    page = drop_words(load_pages("factura_gravadas.json")[0], lambda w: 535 < w.top < 670)
    return build_pdf([page])


SCANNED = build_pdf([Page(612, 792, [])])


def test_good_parse_does_not_call_ai():
    ai = FakeAi([make_record()])
    result = extract_pdf(_pdf(), ai=ai)
    assert ai.calls == 0
    assert result.method == ExtractionMethod.PARSER
    assert result.issues == []


def test_scan_without_ai_is_unreadable():
    result = extract_pdf(SCANNED, ai=None)
    assert result.method == ExtractionMethod.PARSER
    assert result.records == []
    assert _codes(result) == [("pdf_unreadable", IssueSeverity.ERROR)]
    assert "No se pudo leer el PDF" in result.issues[0].message
    assert "escaneado" in result.issues[0].message


def test_garbage_bytes_without_ai():
    result = extract_pdf(b"not a pdf", ai=None)
    assert result.records == []
    assert _codes(result) == [("pdf_unreadable", IssueSeverity.ERROR)]


def test_scan_uses_ai():
    ai = FakeAi([make_record()])
    result = extract_pdf(SCANNED, ai=ai)
    assert ai.calls == 1
    assert result.method == ExtractionMethod.AI
    assert result.records == [make_record()]
    assert _codes(result) == [("ai_extraction_used", IssueSeverity.WARNING)]
    assert "escaneado" in result.issues[0].message


def test_unrecognized_template_uses_ai():
    ai = FakeAi([make_record()])
    from app.extraction.layout import Word

    pdf = build_pdf([Page(612, 792, [Word("RECIBO", 50, 90, 50, 57)])])
    result = extract_pdf(pdf, ai=ai)
    assert result.method == ExtractionMethod.AI
    assert "plantilla" in result.issues[0].message


def test_parser_errors_without_ai_return_parser_issues():
    result = extract_pdf(_pdf_without_totals(), ai=None)
    assert result.method == ExtractionMethod.PARSER
    assert len(result.records) == 1
    assert ("amount_not_found", IssueSeverity.ERROR) in _codes(result)


def test_ai_wins_when_it_has_fewer_errors():
    good = make_record(
        codigo_generacion="5E6F7A8B-9C0D-4E1F-A2B3-C4D5E6F7A8B9",
        total_exentas=Decimal("0.00"),
        total_gravadas=Decimal("54.30"),
        total=Decimal("54.30"),
    )
    result = extract_pdf(_pdf_without_totals(), ai=FakeAi([good]))
    assert result.method == ExtractionMethod.AI
    assert result.records == [good]
    assert _codes(result) == [("ai_extraction_used", IssueSeverity.WARNING)]
    assert result.raw_text  # parser text is kept for reference


def test_parser_kept_when_ai_is_worse():
    bad = make_record(codigo_generacion="x", numero_control="y", total=Decimal("1.00"), emisor_nit=None)
    result = extract_pdf(_pdf_without_totals(), ai=FakeAi([bad]))
    assert result.method == ExtractionMethod.PARSER
    codes = _codes(result)
    assert ("amount_not_found", IssueSeverity.ERROR) in codes
    assert codes[-1] == ("ai_result_discarded", IssueSeverity.WARNING)


def test_tie_keeps_parser():
    parser_only = extract_pdf(_pdf_without_totals(), ai=None)
    assert sum(1 for i in parser_only.issues if i.severity == IssueSeverity.ERROR) == 2
    # Two errors as well: amounts do not reconcile and the emisor NIT is missing.
    ai_record = make_record(total=Decimal("0.00"), emisor_nit=None)
    result = extract_pdf(_pdf_without_totals(), ai=FakeAi([ai_record]))
    assert result.method == ExtractionMethod.PARSER
    assert result.issues[:-1] == parser_only.issues
    assert "(2 errores)" in result.issues[-1].message


def test_ai_exception_falls_back_to_parser_result():
    result = extract_pdf(_pdf_without_totals(), ai=FakeAi(error=AiExtractionError("La IA se negó.")))
    assert result.method == ExtractionMethod.PARSER
    assert len(result.records) == 1
    assert _codes(result)[-1] == ("ai_extraction_failed", IssueSeverity.WARNING)
    assert "La IA se negó." in result.issues[-1].message


def test_unexpected_ai_exception_never_crashes():
    result = extract_pdf(SCANNED, ai=FakeAi(error=RuntimeError("boom")))
    assert result.records == []
    assert _codes(result) == [
        ("pdf_unreadable", IssueSeverity.ERROR),
        ("ai_extraction_failed", IssueSeverity.WARNING),
    ]


def test_ai_with_no_documents():
    result = extract_pdf(SCANNED, ai=FakeAi([]))
    assert result.records == []
    assert _codes(result) == [
        ("pdf_unreadable", IssueSeverity.ERROR),
        ("ai_extraction_failed", IssueSeverity.WARNING),
    ]


def test_ai_result_issues_are_reported():
    result = extract_pdf(SCANNED, ai=FakeAi([make_record(sello_recepcion=None)]))
    assert result.method == ExtractionMethod.AI
    assert _codes(result) == [
        ("ai_extraction_used", IssueSeverity.WARNING),
        ("missing_sello_recepcion", IssueSeverity.WARNING),
    ]


def test_multi_document_issues_name_the_document():
    first = load_pages("factura_exentas_gravadas.json")[0]
    second = drop_words(load_pages("factura_gravadas.json")[0], lambda w: 535 < w.top < 670)
    result = extract_pdf(build_pdf([first, second]), ai=None)
    assert len(result.records) == 2
    assert result.issues
    assert all(i.message.startswith("Documento 2 (5E6F7A8B-") for i in result.issues)
