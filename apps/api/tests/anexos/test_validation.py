import pytest

from app.anexos import (
    RENTA_CATALOG,
    anexo_for_tipo,
    build_sales_anexos,
    effective_renta_codes,
    validate_for_anexo,
)
from app.domain import ClientProfile, IssueSeverity
from tests.anexos.factories import CLIENT, ccf, factura, lines

NO_DEFAULTS = ClientProfile(nit="06140101001010")


@pytest.mark.parametrize(
    ("tipo", "anexo"),
    [
        ("01", 2),
        ("03", 1),
        ("05", 1),
        ("06", 1),
        ("04", None),
        ("07", None),
        ("11", None),
        ("14", None),
        ("", None),
    ],
)
def test_anexo_for_tipo(tipo, anexo):
    assert anexo_for_tipo(tipo) == anexo


def test_renta_catalog_contents():
    operacion = {e["code"]: e["label"] for e in RENTA_CATALOG["tipoOperacion"]}
    ingreso = {e["code"]: e["label"] for e in RENTA_CATALOG["tipoIngreso"]}
    assert list(operacion) == ["1", "2", "3", "4", "12", "13"]
    assert operacion["1"] == "Gravada"
    assert operacion["13"] == "Sujetos pasivos excluidos (Art. 6 LISR)"
    assert list(ingreso) == ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "12", "13"]
    assert ingreso["3"] == "Actividades Comerciales"
    assert ingreso["12"] == operacion["12"]


def test_document_override_beats_client_default():
    doc = factura(1, 1, tipo_operacion_renta="4")
    assert effective_renta_codes(doc, CLIENT) == ("4", "3")
    assert effective_renta_codes(factura(1, 1, tipo_ingreso_renta=" "), CLIENT) == ("1", "3")


def test_renta_override_written_to_anexo1():
    doc = ccf(1, 1, tipo_operacion_renta="13", tipo_ingreso_renta="12")
    result = build_sales_anexos(year=2026, month=10, client=CLIENT, documents=[doc])
    assert lines(result.files[0].content)[0].split(";")[17:20] == ["13", "12", "1"]


def test_renta_missing_from_2025_is_error():
    issues = validate_for_anexo(factura(1, 1, year=2025, month=1), year=2025, month=1, client=NO_DEFAULTS)
    assert {(i.code, i.severity) for i in issues} == {
        ("missing_tipo_operacion_renta", IssueSeverity.ERROR),
        ("missing_tipo_ingreso_renta", IssueSeverity.ERROR),
    }


def test_renta_missing_blocks_build():
    result = build_sales_anexos(year=2026, month=10, client=NO_DEFAULTS, documents=[factura(1, 1)])
    assert result.files == []
    assert {i.code for i in result.issues} == {"missing_tipo_operacion_renta", "missing_tipo_ingreso_renta"}


def test_renta_not_required_before_2025():
    doc = ccf(1, 31, year=2024, month=12)
    assert validate_for_anexo(doc, year=2024, month=12, client=NO_DEFAULTS) == []
    result = build_sales_anexos(year=2024, month=12, client=NO_DEFAULTS, documents=[doc])
    assert lines(result.files[0].content)[0].split(";")[17:19] == ["0", "0"]


def test_unknown_renta_code_is_error():
    client = ClientProfile(default_tipo_operacion="5", default_tipo_ingreso="11")
    issues = validate_for_anexo(factura(1, 1), year=2026, month=10, client=client)
    assert {i.code for i in issues} == {"unknown_tipo_operacion_renta", "unknown_tipo_ingreso_renta"}
    assert all(i.severity is IssueSeverity.ERROR for i in issues)


def test_unmapped_tipo_is_skipped_with_warning():
    other = factura(9, 1, gravadas="5.00")
    other.record.tipo_dte = "11"
    result = build_sales_anexos(
        year=2026, month=10, client=CLIENT, documents=[other, factura(1, 1, gravadas="1")]
    )
    assert [f.anexo for f in result.files] == [2]
    [issue] = result.issues
    assert (issue.code, issue.severity, issue.field) == (
        "tipo_not_in_sales_anexo",
        IssueSeverity.WARNING,
        "tipo_dte",
    )
    assert validate_for_anexo(other, year=2026, month=10, client=CLIENT) == []


def test_no_documents_no_files():
    result = build_sales_anexos(year=2026, month=10, client=CLIENT, documents=[])
    assert result.files == [] and result.issues == []


def test_negative_amount_is_error():
    doc = factura(1, 1, gravadas="-1.00")
    issues = validate_for_anexo(doc, year=2026, month=10, client=CLIENT)
    assert [(i.code, i.field) for i in issues] == [("negative_amount", "total_gravadas")]


def test_out_of_period_blocks_build():
    result = build_sales_anexos(year=2026, month=10, client=CLIENT, documents=[factura(1, 30, month=9)])
    assert result.files == []
    assert [i.code for i in result.issues] == ["outside_period"]


def test_missing_required_anexo1_fields():
    doc = ccf(1, 1)
    doc.record.sello_recepcion = None
    doc.record.numero_control = " "
    doc.record.receptor_nombre = None
    codes = {i.code for i in validate_for_anexo(doc, year=2026, month=10, client=CLIENT)}
    assert codes == {"missing_sello_recepcion", "missing_numero_control", "missing_receptor_nombre"}


def test_missing_fecha_is_error():
    doc = factura(1, 1)
    doc.record.fecha_emision = None
    assert [i.code for i in validate_for_anexo(doc, year=2026, month=10, client=CLIENT)] == [
        "missing_fecha_emision"
    ]


def test_period_before_any_spec_is_error():
    doc = factura(1, 1, year=2021, month=5)
    codes = [i.code for i in validate_for_anexo(doc, year=2021, month=5, client=CLIENT)]
    assert codes == ["anexo_spec_not_found"]


def test_invalid_month_raises():
    with pytest.raises(ValueError):
        build_sales_anexos(year=2026, month=13, client=CLIENT, documents=[])


def test_unencodable_characters_replaced_with_warning():
    doc = ccf(1, 1, nombre="Dvořák Łódź 😀 Ñuñoa")
    validation = validate_for_anexo(doc, year=2026, month=10, client=CLIENT)
    assert [i.code for i in validation] == ["character_not_encodable"]

    result = build_sales_anexos(year=2026, month=10, client=CLIENT, documents=[doc])
    assert lines(result.files[0].content)[0].split(";")[8] == "Dvorák ?ódz ? Ñuñoa"
    [issue] = result.issues  # validation and writer warnings are deduplicated
    assert issue.code == "character_not_encodable"
    assert issue.severity is IssueSeverity.WARNING
    assert issue.field == "receptor_nombre"
    assert all(ch in issue.message for ch in "řŁź😀")


def test_delimiter_and_line_breaks_in_text_are_neutralized():
    doc = ccf(1, 1, nombre="Comercial; Uno\r\nS.A.")
    result = build_sales_anexos(year=2026, month=10, client=CLIENT, documents=[doc])
    [row] = lines(result.files[0].content)
    assert len(row.split(";")) == 20
    assert row.split(";")[8] == "Comercial, Uno S.A."
    assert [i.code for i in result.issues] == ["delimiter_in_text"]


def test_file_format_encoding_crlf_no_header():
    docs = [
        ccf(1, 1, nombre="Señora Muñoz"),
        ccf(2, 2),
        factura(1, 1, gravadas="1"),
        factura(2, 2, gravadas="2"),
    ]
    result = build_sales_anexos(year=2026, month=10, client=CLIENT, documents=docs)
    for f in result.files:
        assert len(f.file_name) <= 25
        assert f.content.count(b"\r\n") == f.row_count
        assert b"\n" not in f.content.replace(b"\r\n", b"")
        assert f.content[:10] in (b"01/10/2026", b"02/10/2026")  # sin encabezado
        assert b"\xef\xbb\xbf" not in f.content  # sin BOM
    anexo1 = next(f for f in result.files if f.anexo == 1)
    assert "Señora Muñoz".encode("windows-1252") in anexo1.content
    assert "Señora Muñoz".encode() not in anexo1.content
