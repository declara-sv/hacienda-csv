import datetime as dt

from app.anexos import build_sales_anexos
from app.domain import IssueSeverity
from tests.anexos.factories import CLIENT, ccf, code, factura, lines

CCF1 = code(1, "CCCCCCCC")
CTRL1 = "DTE-03-M001P001-000000000000001"
SELLO1 = "2026A1B2C3D4E5F6A7B8C9D0E1F2A3B400000001"


def _cells(result, index=0):
    [anexo1] = [f for f in result.files if f.anexo == 1]
    return lines(anexo1.content)[index].split(";")


def test_golden_row_with_14_digit_nit():
    doc = ccf(1, 7, gravadas="100.00", nit="0614-010190-101-3")
    result = build_sales_anexos(year=2026, month=10, client=CLIENT, documents=[doc])

    assert result.issues == []
    [anexo1] = result.files
    assert anexo1.file_name == "anexo1_202610.csv"
    assert anexo1.row_count == 1
    assert anexo1.content == (
        f"07/10/2026;4;03;{CTRL1};{SELLO1};{CCF1};;06140101901013;Empresa Ficticia, S.A. de C.V.;"
        "0.00;0.00;100.00;13.00;0.00;0.00;113.00;;1;3;1\r\n"
    ).encode("windows-1252")


def test_receptor_identification_variants():
    docs = [
        ccf(1, 1, nit="06140101901013"),  # 14 dígitos
        ccf(2, 2, nit="2101708101018"),  # 13 dígitos -> 0 a la izquierda
        ccf(3, 3, nit="01234567-8"),  # 9 dígitos -> DUI homologado en Q
        ccf(4, 4, nit=None, dui="1234567-8"),  # DUI de 8 dígitos -> 0 a la izquierda
        ccf(5, 5, nit=None, dui="02345678-9"),
    ]
    result = build_sales_anexos(year=2026, month=10, client=CLIENT, documents=docs)
    assert result.issues == []
    ids = [(c[7], c[16]) for c in (_cells(result, i) for i in range(5))]
    assert ids == [
        ("06140101901013", ""),
        ("02101708101018", ""),
        ("", "012345678"),
        ("", "012345678"),
        ("", "023456789"),
    ]


def test_nit_wins_over_dui_never_both():
    result = build_sales_anexos(
        year=2026, month=10, client=CLIENT, documents=[ccf(1, 1, nit="06140101901013", dui="012345678")]
    )
    cells = _cells(result)
    assert (cells[7], cells[16]) == ("06140101901013", "")


def test_invalid_nit_blocks_generation():
    result = build_sales_anexos(
        year=2026,
        month=10,
        client=CLIENT,
        documents=[ccf(1, 1, nit="0614-0101"), factura(9, 1, gravadas="1")],
    )
    assert result.files == []
    [issue] = result.issues
    assert issue.code == "invalid_receptor_nit"
    assert issue.severity is IssueSeverity.ERROR
    assert issue.message.startswith(f"Documento {CCF1}: ")


def test_nrc_fallback_warns():
    result = build_sales_anexos(
        year=2026, month=10, client=CLIENT, documents=[ccf(1, 1, nit=None, nrc="123456-7")]
    )
    assert _cells(result)[7] == "1234567"
    assert [i.code for i in result.issues] == ["receptor_nrc_used"]


def test_missing_receptor_id_is_error():
    result = build_sales_anexos(
        year=2026, month=10, client=CLIENT, documents=[ccf(1, 1, nit=None, dui=None, nrc=None)]
    )
    assert result.files == []
    assert [i.code for i in result.issues] == ["missing_receptor_id"]


def test_rows_sorted_by_date_and_time_and_tipos():
    docs = [
        ccf(3, 9, tipo="06", gravadas="10.00"),
        ccf(2, 2, tipo="05", gravadas="20.00", hora=dt.time(16)),
        ccf(1, 2, gravadas="30.00", hora=dt.time(8)),
    ]
    result = build_sales_anexos(year=2026, month=10, client=CLIENT, documents=docs)
    rows = [_cells(result, i) for i in range(3)]
    assert [(r[0], r[2], r[11], r[12], r[15]) for r in rows] == [
        ("02/10/2026", "03", "30.00", "3.90", "33.90"),
        ("02/10/2026", "05", "20.00", "2.60", "22.60"),
        ("09/10/2026", "06", "10.00", "1.30", "11.30"),
    ]
    assert all(len(r) == 20 and r[19] == "1" for r in rows)


def test_exentas_and_no_sujetas_sum_into_total():
    doc = ccf(1, 1, gravadas="50.00", exentas="5.00", no_sujetas="7.25")
    cells = _cells(build_sales_anexos(year=2026, month=10, client=CLIENT, documents=[doc]))
    assert cells[9:16] == ["5.00", "7.25", "50.00", "6.50", "0.00", "0.00", "68.75"]


def test_iva_mismatch_is_warning_only():
    result = build_sales_anexos(
        year=2026, month=10, client=CLIENT, documents=[ccf(1, 1, gravadas="100.00", iva="12.00")]
    )
    assert len(result.files) == 1
    [issue] = result.issues
    assert issue.code == "iva_mismatch"
    assert issue.severity is IssueSeverity.WARNING


def test_debito_fiscal_within_one_cent_is_accepted():
    result = build_sales_anexos(
        year=2026, month=10, client=CLIENT, documents=[ccf(1, 1, gravadas="100.00", iva="13.01")]
    )
    assert result.issues == []


def test_both_anexos_generated_together():
    docs = [ccf(1, 1), factura(1, 1, gravadas="5.00")]
    result = build_sales_anexos(year=2026, month=10, client=CLIENT, documents=docs)
    assert sorted((f.anexo, f.file_name, f.row_count) for f in result.files) == [
        (1, "anexo1_202610.csv", 1),
        (2, "anexo2_202610.csv", 1),
    ]
