import copy
import datetime as dt
import json
from importlib import resources

import pytest

from app.anexos import build_sales_anexos
from app.anexos import builder as builder_module
from app.anexos import validation as validation_module
from app.anexos.spec import (
    SpecError,
    SpecRegistry,
    default_registry,
    load_registry,
    load_spec_file,
    parse_spec,
)
from app.anexos.writer import RenderRow, render_csv
from tests.anexos.factories import CLIENT, ccf, code, factura, lines


def _raw(anexo: int) -> dict:
    path = resources.files("app.anexos").joinpath("specs", f"f07_anexo{anexo}_v2025.json")
    return json.loads(path.read_text(encoding="utf-8"))


def _column(spec: dict, letter: str) -> dict:
    return next(c for c in spec["columns"] if c["letter"] == letter)


def test_bundled_specs_load():
    registry = default_registry()
    a1 = registry.for_period(1, 2026, 10)
    a2 = registry.for_period(2, 2026, 10)
    assert (a1.spec_id, len(a1.columns)) == ("f07_anexo1_v2025", 20)
    assert (a2.spec_id, len(a2.columns)) == ("f07_anexo2_v2025", 23)
    for spec in (a1, a2):
        assert spec.file.delimiter == ";"
        assert spec.file.line_ending == "\r\n"
        assert spec.file.encoding == "windows-1252"
        assert spec.file.header is False
        assert not any(c.strip_dashes for c in spec.columns)
    assert registry.for_period(1, 2022, 10) is None


@pytest.mark.parametrize(("year", "month"), [(2022, 11), (2026, 1), (2099, 12)])
def test_file_names_at_most_25_chars(year, month):
    registry = default_registry()
    for anexo in (1, 2):
        name = registry.for_period(anexo, year, month).file_name(year, month)
        assert len(name) <= 25
        assert name == f"anexo{anexo}_{year}{month:02d}.csv"


def _mutate(anexo, fn):
    spec = copy.deepcopy(_raw(anexo))
    fn(spec)
    return spec


MALFORMED = {
    "letters_out_of_order": lambda s: s["columns"].__setitem__(slice(0, 2), s["columns"][1::-1]),
    "missing_column": lambda s: s["columns"].pop(5),
    "field_without_source": lambda s: s["columns"][0].pop("source"),
    "unknown_source": lambda s: s["columns"][0].update(source="fecha"),
    "constant_without_value": lambda s: s["columns"][1].pop("value"),
    "constant_with_source": lambda s: s["columns"][1].update(source="tipo_dte"),
    "unknown_format": lambda s: s["columns"][0].update(format="datetime"),
    "strip_dashes_on_money": lambda s: s["columns"][9].update(strip_dashes=True),
    "constant_too_wide": lambda s: s["columns"][1].update(value="04"),
    "negative_money_constant": lambda s: s["columns"][13].update(value="-1.00"),
    "sum_of_unknown_letter": lambda s: s["columns"][15].update(sum_of=["J", "Z"]),
    "sum_of_text_column": lambda s: s["columns"][15].update(sum_of=["I", "J"]),
    "last_column_not_anexo": lambda s: s["columns"][-1].update(value="2"),
    "extra_key": lambda s: s.update(extra=True),
    "extra_column_key": lambda s: s["columns"][0].update(padding="left"),
    "header_true": lambda s: s["file"].update(header=True),
    "bad_encoding": lambda s: s["file"].update(encoding="klingon-8"),
    "bad_line_ending": lambda s: s["file"].update(line_ending="\r"),
    "multi_char_delimiter": lambda s: s["file"].update(delimiter=";;"),
    "file_name_too_long": lambda s: s["file"].update(file_name_pattern="anexo_contribuyentes_{yyyymm}.csv"),
    "file_name_unknown_placeholder": lambda s: s["file"].update(file_name_pattern="anexo1_{period}.csv"),
    "bad_valid_from": lambda s: s.update(valid_from="2025-13"),
    "valid_to_before_from": lambda s: s.update(valid_to="2020-01"),
    "unsupported_anexo": lambda s: s.update(anexo=7),
}


@pytest.mark.parametrize("name", sorted(MALFORMED))
def test_parse_spec_rejects_malformed(name):
    with pytest.raises(SpecError):
        parse_spec(_mutate(1, MALFORMED[name]))


def test_load_spec_file_rejects_invalid_json(tmp_path):
    path = tmp_path / "f07_anexo1_vbad.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(SpecError):
        load_spec_file(path)


def test_registry_rejects_overlap_and_selects_by_period(tmp_path):
    old = _mutate(1, lambda s: s.update(valid_to="2026-12"))
    new = _mutate(1, lambda s: s.update(spec_id="f07_anexo1_v2027", version="2027", valid_from="2027-01"))
    _column(new, "I")["name"] = "Nombre del cliente (2027)"
    (tmp_path / "f07_anexo1_v2025.json").write_text(json.dumps(old), encoding="utf-8")
    (tmp_path / "f07_anexo1_v2027.json").write_text(json.dumps(new), encoding="utf-8")
    (tmp_path / "notes.json").write_text("ignored", encoding="utf-8")

    registry = load_registry(tmp_path)
    assert registry.for_period(1, 2026, 12).spec_id == "f07_anexo1_v2025"
    assert registry.for_period(1, 2027, 1).spec_id == "f07_anexo1_v2027"

    with pytest.raises(SpecError, match="traslapan"):
        SpecRegistry([parse_spec(_raw(1)), parse_spec(new)])


def test_registry_requires_at_least_one_spec(tmp_path):
    with pytest.raises(SpecError):
        load_registry(tmp_path)


def _strip_dashes_registry():
    a1 = _raw(1)
    for letter in ("D", "E", "F"):
        _column(a1, letter)["strip_dashes"] = True
    a2 = _raw(2)
    for letter in ("H", "I"):
        _column(a2, letter)["strip_dashes"] = True
    return SpecRegistry([parse_spec(a1), parse_spec(a2)])


def test_strip_dashes_option_end_to_end(monkeypatch):
    registry = _strip_dashes_registry()
    monkeypatch.setattr(builder_module, "default_registry", lambda: registry)
    monkeypatch.setattr(validation_module, "default_registry", lambda: registry)

    result = build_sales_anexos(
        year=2026, month=10, client=CLIENT, documents=[ccf(1, 1), factura(1, 1, gravadas="1")]
    )
    by_anexo = {f.anexo: lines(f.content)[0].split(";") for f in result.files}
    assert by_anexo[1][3] == "DTE03M001P001000000000000001"
    assert by_anexo[1][5] == code(1, "CCCCCCCC").replace("-", "")
    assert by_anexo[2][7] == by_anexo[2][8] == code(1).replace("-", "")


def test_writer_pads_fixed_width_and_reports_overflow():
    spec = parse_spec(_raw(2))
    ok = render_csv(spec, [RenderRow(label="x", values=_anexo2_values(tipo="1"))])
    assert ok.content.split(b";")[2] == b"01"
    bad = render_csv(spec, [RenderRow(label="x", values=_anexo2_values(tipo="001"))])
    [issue] = bad.issues
    assert issue.code == "value_exceeds_width"


def _anexo2_values(tipo):
    return {
        "fecha_emision": dt.date(2026, 10, 1),
        "tipo_dte": tipo,
        "codigo_generacion_del": "a",
        "codigo_generacion_al": "b",
        "tipo_operacion_renta": "1",
        "tipo_ingreso_renta": "3",
    }
