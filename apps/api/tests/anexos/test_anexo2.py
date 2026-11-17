import datetime as dt

from app.anexos import build_sales_anexos
from app.domain import ClientProfile, IssueSeverity
from tests.anexos.factories import CLIENT, code, factura, lines

C1, C2, C3, C4, C5 = (code(n) for n in range(1, 6))


def _three_days():
    return [
        factura(5, 5, hora=dt.time(15, 0), gravadas="10.00"),
        factura(2, 2, gravadas="54.30"),
        factura(3, 5, hora=dt.time(15, 0), gravadas="5.25", no_sujetas="3.00"),
        factura(1, 1, exentas="2.50", gravadas="48.14"),
        factura(4, 5, hora=dt.time(8, 30), gravadas="20.00", exentas="1.00"),
    ]


def test_golden_rows_grouped_by_day():
    result = build_sales_anexos(year=2026, month=10, client=CLIENT, documents=_three_days())

    assert result.issues == []
    [anexo2] = result.files
    assert anexo2.anexo == 2
    assert anexo2.file_name == "anexo2_202610.csv"
    assert anexo2.row_count == 3
    assert anexo2.content == (
        f"01/10/2026;4;01;N/A;N/A;N/A;N/A;{C1};{C1};;2.50;0.00;0.00;48.14;0.00;0.00;0.00;0.00;0.00;50.64;1;3;2\r\n"
        f"02/10/2026;4;01;N/A;N/A;N/A;N/A;{C2};{C2};;0.00;0.00;0.00;54.30;0.00;0.00;0.00;0.00;0.00;54.30;1;3;2\r\n"
        f"05/10/2026;4;01;N/A;N/A;N/A;N/A;{C4};{C5};;1.00;0.00;3.00;35.25;0.00;0.00;0.00;0.00;0.00;39.25;1;3;2\r\n"
    ).encode("windows-1252")


def test_codes_keep_dashes_and_row_has_23_columns():
    result = build_sales_anexos(year=2026, month=10, client=CLIENT, documents=[factura(1, 1, gravadas="1")])
    [row] = lines(result.files[0].content)
    cells = row.split(";")
    assert len(cells) == 23
    assert cells[7] == C1 and "-" in cells[7]
    assert cells[9] == ""  # J máquina registradora vacío, nunca 0
    assert cells[22] == "2"


def test_same_day_splits_by_effective_renta_codes():
    docs = [
        factura(1, 3, hora=dt.time(8), gravadas="10.00"),
        factura(2, 3, hora=dt.time(9), gravadas="20.00", tipo_operacion_renta="4"),
        factura(3, 3, hora=dt.time(10), gravadas="30.00"),
        factura(4, 3, hora=dt.time(11), gravadas="40.00", tipo_ingreso_renta="2"),
    ]
    result = build_sales_anexos(year=2026, month=10, client=CLIENT, documents=docs)
    rows = [r.split(";") for r in lines(result.files[0].content)]
    summary = [(r[7], r[8], r[13], r[20], r[21]) for r in rows]
    assert summary == [
        (code(1), code(3), "40.00", "1", "3"),
        (code(2), code(2), "20.00", "4", "3"),
        (code(4), code(4), "40.00", "1", "2"),
    ]


def test_missing_hora_sorts_last_within_day_with_warning():
    docs = [factura(1, 4, hora=None, gravadas="1.00"), factura(2, 4, hora=dt.time(23, 59), gravadas="1.00")]
    result = build_sales_anexos(year=2026, month=10, client=CLIENT, documents=docs)
    [row] = lines(result.files[0].content)
    cells = row.split(";")
    assert (cells[7], cells[8]) == (code(2), code(1))
    assert [i.code for i in result.issues] == ["missing_hora_emision"]
    assert result.issues[0].severity is IssueSeverity.WARNING


def test_pre_2025_renta_columns_are_zero_without_defaults():
    client = ClientProfile()
    doc = factura(1, 15, gravadas="11.30", year=2024, month=12)
    result = build_sales_anexos(year=2024, month=12, client=client, documents=[doc])
    assert result.issues == []
    [anexo2] = result.files
    assert anexo2.file_name == "anexo2_202412.csv"
    cells = lines(anexo2.content)[0].split(";")
    assert cells[20:] == ["0", "0", "2"]


def test_pre_2025_ignores_overrides():
    doc = factura(1, 15, gravadas="11.30", year=2024, month=6, tipo_operacion_renta="1")
    result = build_sales_anexos(year=2024, month=6, client=CLIENT, documents=[doc])
    assert lines(result.files[0].content)[0].split(";")[20:22] == ["0", "0"]


def test_amounts_round_half_up():
    docs = [factura(1, 1, gravadas="0.005"), factura(2, 1, hora=dt.time(10), gravadas="1.125")]
    result = build_sales_anexos(year=2026, month=10, client=CLIENT, documents=docs)
    cells = lines(result.files[0].content)[0].split(";")
    assert cells[13] == "1.14"  # 0.01 + 1.13
    assert cells[19] == "1.14"
