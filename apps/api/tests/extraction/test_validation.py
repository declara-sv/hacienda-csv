import datetime as dt
from decimal import Decimal

import pytest

from app.domain import ClientProfile, IssueSeverity
from app.extraction import find_duplicate_codes, validate_in_period, validate_record

from .support import make_ccf, make_record


def _codes(issues):
    return {(i.code, i.severity, i.field) for i in issues}


E, W = IssueSeverity.ERROR, IssueSeverity.WARNING


def test_valid_factura_and_ccf_have_no_issues():
    assert validate_record(make_record()) == []
    assert validate_record(make_ccf()) == []


def test_lowercase_codigo_is_accepted_as_printed():
    assert validate_record(make_record(codigo_generacion="0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d")) == []


@pytest.mark.parametrize(
    "field",
    ["codigo_generacion", "numero_control", "fecha_emision", "emisor_nit"],
)
def test_required_fields(field):
    issues = validate_record(make_record(**{field: None}))
    assert ("missing_required_field", E, field) in _codes(issues)


def test_missing_tipo():
    assert ("missing_required_field", E, "tipo_dte") in _codes(validate_record(make_record(tipo_dte="")))


def test_unknown_tipo():
    assert ("invalid_tipo_dte", E, "tipo_dte") in _codes(validate_record(make_record(tipo_dte="99")))


@pytest.mark.parametrize(
    "codigo",
    [
        "0A1B2C3D4E5F4A6B8C7D9E0F1A2B3C4D",
        "0A1B2C3D-4E5F-4A6B-8C7D-9E0F1A2B3C4",
        "ZZZZZZZZ-4E5F-4A6B-8C7D-9E0F1A2B3C4D",
    ],
)
def test_invalid_codigo_generacion(codigo):
    issues = validate_record(make_record(codigo_generacion=codigo))
    assert ("invalid_codigo_generacion", E, "codigo_generacion") in _codes(issues)


@pytest.mark.parametrize(
    "control", ["DTE-01-M001P001-26", "01-M001P001-000000000000101", "DTE-01-M001-000000000000101"]
)
def test_invalid_numero_control(control):
    issues = validate_record(make_record(numero_control=control))
    assert ("invalid_numero_control", E, "numero_control") in _codes(issues)


def test_numero_control_must_match_tipo():
    issues = validate_record(make_record(numero_control="DTE-03-M001P001-000000000000101"))
    assert ("numero_control_tipo_mismatch", E, "numero_control") in _codes(issues)


def test_missing_sello_is_warning_for_factura_and_error_for_ccf():
    assert _codes(validate_record(make_record(sello_recepcion=None))) == {
        ("missing_sello_recepcion", W, "sello_recepcion")
    }
    assert ("missing_sello_recepcion", E, "sello_recepcion") in _codes(
        validate_record(make_ccf(sello_recepcion="-"))
    )


def test_negative_amounts():
    issues = validate_record(make_record(total_exentas=Decimal("-2.50"), total_gravadas=Decimal("53.14")))
    assert ("negative_amount", E, "total_exentas") in _codes(issues)


def test_amounts_must_reconcile():
    issues = validate_record(make_record(total=Decimal("50.66")))
    assert ("amounts_do_not_reconcile", E, "total") in _codes(issues)


def test_reconcile_tolerance_is_one_cent():
    assert validate_record(make_record(total=Decimal("50.65"))) == []


def test_ccf_iva_mismatch_is_a_warning():
    record = make_ccf(iva=Decimal("12.00"), total=Decimal("112.00"))
    assert _codes(validate_record(record)) == {("iva_mismatch", W, "iva")}


def test_ccf_iva_rounding():
    record = make_ccf(total_gravadas=Decimal("10.05"), iva=Decimal("1.31"), total=Decimal("11.36"))
    assert validate_record(record) == []


def test_factura_must_not_split_iva():
    record = make_record(total_gravadas=Decimal("42.60"), iva=Decimal("5.54"))
    assert ("factura_iva_not_zero", E, "iva") in _codes(validate_record(record))


def test_ccf_needs_receptor_id():
    issues = validate_record(make_ccf(receptor_nit=None))
    assert ("missing_receptor_id", E, "receptor_nit") in _codes(issues)
    assert validate_record(make_ccf(receptor_nit=None, receptor_dui="04567890-1")) == []


def test_in_period_ok():
    client = ClientProfile(nit="0123-4567-8", nrc="12345")
    assert validate_in_period(make_record(), year=2026, month=10, client=client) == []


def test_outside_period():
    issues = validate_in_period(make_record(), year=2026, month=9, client=ClientProfile())
    assert _codes(issues) == {("outside_period", E, "fecha_emision")}


def test_emisor_must_be_the_client():
    issues = validate_in_period(
        make_record(), year=2026, month=10, client=ClientProfile(nit="06140101011011")
    )
    assert _codes(issues) == {("not_client_sale", E, "emisor_nit")}
    assert "no es una venta del cliente" in issues[0].message

    issues = validate_in_period(make_record(), year=2026, month=10, client=ClientProfile(nrc="9999-9"))
    assert _codes(issues) == {("not_client_sale", E, "emisor_nrc")}


def test_client_without_ids_skips_emisor_check():
    assert validate_in_period(make_record(emisor_nit="9"), year=2026, month=10, client=ClientProfile()) == []


def test_tipos_outside_sales_anexos_are_warnings():
    record = make_record(tipo_dte="14", numero_control="DTE-14-M001P001-000000000000101")
    assert _codes(validate_in_period(record, year=2026, month=10, client=ClientProfile())) == {
        ("not_exported_to_sales_anexos", W, "tipo_dte")
    }


def test_missing_fecha_is_not_reported_twice():
    assert (
        validate_in_period(make_record(fecha_emision=None), year=2026, month=10, client=ClientProfile()) == []
    )


def test_period_boundaries():
    client = ClientProfile()
    assert (
        validate_in_period(
            make_record(fecha_emision=dt.date(2026, 10, 31)), year=2026, month=10, client=client
        )
        == []
    )
    assert validate_in_period(
        make_record(fecha_emision=dt.date(2025, 10, 1)), year=2026, month=10, client=client
    )


def test_duplicate_codes():
    result = find_duplicate_codes(
        [
            ("a", "0A1B2C3D-4E5F-4A6B-8C7D-9E0F1A2B3C4D"),
            ("b", "0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d"),
            ("c", "5E6F7A8B-9C0D-4E1F-A2B3-C4D5E6F7A8B9"),
            ("d", None),
            ("e", ""),
        ]
    )
    assert set(result) == {"a", "b", "c", "d", "e"}
    for doc_id in ("a", "b"):
        assert _codes(result[doc_id]) == {("duplicate_codigo_generacion", E, "codigo_generacion")}
        assert "2 documentos" in result[doc_id][0].message
    assert result["c"] == result["d"] == result["e"] == []


def test_same_document_listed_twice_is_not_a_duplicate():
    result = find_duplicate_codes([("a", "X"), ("a", "X")])
    assert result == {"a": []}
