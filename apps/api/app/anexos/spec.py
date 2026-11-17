"""F-07 anexo specifications as data.

Each anexo layout lives in a versioned JSON file under ``app/anexos/specs/``. A spec says which
columns go in which order, where each value comes from, and how it is formatted, plus file-level
settings (delimiter, line ending, encoding, file name). The CSV writer renders purely from the
spec, so a manual revision means adding a new JSON file with a new validity range.
"""

from __future__ import annotations

import codecs
import json
import re
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from functools import lru_cache
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

SPEC_FILE_GLOB = re.compile(r"^f07_anexo\d+_v[\w.-]+\.json$")
_PERIOD_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
_FILE_NAME_PLACEHOLDERS = {"yyyymm": "202601", "yyyy": "2026", "mm": "01", "anexo": "1"}

# Keys the builder fills for each anexo row. A spec column of kind "field" must use one of these.
SOURCE_KEYS: dict[int, frozenset[str]] = {
    1: frozenset(
        {
            "fecha_emision",
            "tipo_dte",
            "numero_control",
            "sello_recepcion",
            "codigo_generacion",
            "receptor_nit_nrc",
            "receptor_nombre",
            "receptor_dui",
            "total_exentas",
            "total_no_sujetas",
            "total_gravadas",
            "iva",
            "tipo_operacion_renta",
            "tipo_ingreso_renta",
        }
    ),
    2: frozenset(
        {
            "fecha_emision",
            "tipo_dte",
            "codigo_generacion_del",
            "codigo_generacion_al",
            "total_exentas",
            "total_no_sujetas",
            "total_gravadas",
            "tipo_operacion_renta",
            "tipo_ingreso_renta",
        }
    ),
}


class SpecError(ValueError):
    """A spec file is missing, malformed, or inconsistent with the other specs."""


class ColumnKind(StrEnum):
    FIELD = "field"
    CONSTANT = "constant"
    SUM = "sum"


class ColumnFormat(StrEnum):
    TEXT = "text"
    DATE = "date"  # DD/MM/AAAA
    MONEY = "money"  # 2 decimals, decimal point, no thousands separator


def column_letter(index: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA."""
    letters = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        letters = chr(ord("A") + rem) + letters
    return letters


def parse_period(value: str) -> tuple[int, int]:
    match = _PERIOD_RE.match(value)
    if not match:
        raise ValueError(f"período {value!r} inválido; se espera AAAA-MM")
    return int(match.group(1)), int(match.group(2))


class ColumnSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    letter: str
    name: str = Field(min_length=1)
    kind: ColumnKind
    format: ColumnFormat = ColumnFormat.TEXT
    source: str | None = None
    value: str | None = None
    sum_of: tuple[str, ...] = ()
    width: int | None = Field(default=None, ge=1, description="Fixed width; shorter values are left-padded.")
    pad_char: str = Field(default="0", min_length=1, max_length=1)
    strip_dashes: bool = False

    @model_validator(mode="after")
    def _check_kind(self) -> Self:
        where = f"columna {self.letter}"
        if self.kind is ColumnKind.FIELD:
            if not self.source:
                raise ValueError(f"{where}: kind 'field' requiere 'source'")
            if self.value is not None or self.sum_of:
                raise ValueError(f"{where}: kind 'field' no admite 'value' ni 'sum_of'")
        elif self.kind is ColumnKind.CONSTANT:
            if self.value is None:
                raise ValueError(f"{where}: kind 'constant' requiere 'value'")
            if self.source or self.sum_of:
                raise ValueError(f"{where}: kind 'constant' no admite 'source' ni 'sum_of'")
            if self.format is ColumnFormat.DATE:
                raise ValueError(f"{where}: una constante no puede tener formato 'date'")
            if self.format is ColumnFormat.MONEY:
                try:
                    amount = Decimal(self.value)
                except InvalidOperation:
                    raise ValueError(f"{where}: {self.value!r} no es un monto") from None
                if amount < 0:
                    raise ValueError(f"{where}: los montos no pueden ser negativos")
        elif self.kind is ColumnKind.SUM:
            if not self.sum_of:
                raise ValueError(f"{where}: kind 'sum' requiere 'sum_of'")
            if self.format is not ColumnFormat.MONEY:
                raise ValueError(f"{where}: kind 'sum' debe tener formato 'money'")
            if self.source or self.value is not None:
                raise ValueError(f"{where}: kind 'sum' no admite 'source' ni 'value'")
        if self.format is not ColumnFormat.TEXT and (self.width is not None or self.strip_dashes):
            raise ValueError(f"{where}: 'width' y 'strip_dashes' solo aplican a formato 'text'")
        if self.kind is ColumnKind.CONSTANT and self.width is not None and len(self.value or "") > self.width:
            raise ValueError(f"{where}: la constante excede el ancho {self.width}")
        return self


class FileSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    delimiter: str = Field(min_length=1, max_length=1)
    line_ending: Literal["\r\n", "\n"]
    encoding: str
    header: Literal[False] = False
    file_name_pattern: str
    max_file_name_length: int = Field(default=25, ge=1)

    @field_validator("delimiter")
    @classmethod
    def _delimiter(cls, value: str) -> str:
        if value.isalnum() or value in "\r\n.-/":
            raise ValueError(f"delimitador {value!r} no permitido")
        return value

    @field_validator("encoding")
    @classmethod
    def _encoding(cls, value: str) -> str:
        try:
            codecs.lookup(value)
        except LookupError:
            raise ValueError(f"codificación desconocida {value!r}") from None
        return value

    @model_validator(mode="after")
    def _file_name(self) -> Self:
        try:
            sample = self.file_name_pattern.format(**_FILE_NAME_PLACEHOLDERS)
        except (KeyError, IndexError, ValueError) as exc:
            allowed = ", ".join("{" + k + "}" for k in _FILE_NAME_PLACEHOLDERS)
            raise ValueError(f"file_name_pattern inválido ({exc}); variables permitidas: {allowed}") from None
        if len(sample) > self.max_file_name_length:
            raise ValueError(f"el nombre de archivo {sample!r} excede {self.max_file_name_length} caracteres")
        if any(ch in sample for ch in '\\/:*?"<>|'):
            raise ValueError(f"el nombre de archivo {sample!r} contiene caracteres no permitidos")
        return self


class AnexoSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    spec_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    anexo: int = Field(ge=1)
    description: str = ""
    valid_from: str
    valid_to: str | None = None
    column_count: int = Field(ge=1)
    file: FileSpec
    columns: tuple[ColumnSpec, ...]

    @field_validator("valid_from", "valid_to")
    @classmethod
    def _period(cls, value: str | None) -> str | None:
        if value is not None:
            parse_period(value)
        return value

    @model_validator(mode="after")
    def _check_columns(self) -> Self:
        if self.anexo not in SOURCE_KEYS:
            raise ValueError(f"el anexo {self.anexo} no está soportado")
        if self.valid_to is not None and parse_period(self.valid_to) < parse_period(self.valid_from):
            raise ValueError("valid_to es anterior a valid_from")
        if len(self.columns) != self.column_count:
            raise ValueError(f"se declararon {self.column_count} columnas pero hay {len(self.columns)}")

        by_letter: dict[str, ColumnSpec] = {}
        for index, column in enumerate(self.columns):
            expected = column_letter(index)
            if column.letter != expected:
                raise ValueError(f"la columna {index + 1} debe ser {expected}, no {column.letter}")
            by_letter[column.letter] = column

        known = SOURCE_KEYS[self.anexo]
        for column in self.columns:
            if column.kind is ColumnKind.FIELD and column.source not in known:
                raise ValueError(
                    f"columna {column.letter}: source {column.source!r} desconocido "
                    f"para el anexo {self.anexo}"
                )
            for ref in column.sum_of:
                target = by_letter.get(ref)
                if target is None or ref == column.letter:
                    raise ValueError(f"columna {column.letter}: sum_of referencia inválida {ref!r}")
                if target.format is not ColumnFormat.MONEY or target.kind is ColumnKind.SUM:
                    raise ValueError(
                        f"columna {column.letter}: sum_of {ref!r} debe ser una columna de monto no calculada"
                    )

        last = self.columns[-1]
        if last.kind is not ColumnKind.CONSTANT or last.value != str(self.anexo):
            raise ValueError(f"la última columna debe ser la constante {self.anexo!r} (número de anexo)")
        return self

    def covers(self, year: int, month: int) -> bool:
        period = (year, month)
        if period < parse_period(self.valid_from):
            return False
        return self.valid_to is None or period <= parse_period(self.valid_to)

    def file_name(self, year: int, month: int) -> str:
        return self.file.file_name_pattern.format(
            yyyymm=f"{year:04d}{month:02d}", yyyy=f"{year:04d}", mm=f"{month:02d}", anexo=str(self.anexo)
        )


def parse_spec(data: object, *, origin: str = "<spec>") -> AnexoSpec:
    try:
        return AnexoSpec.model_validate(data)
    except ValidationError as exc:
        raise SpecError(f"especificación inválida {origin}: {exc}") from exc


def load_spec_file(path: Path | Traversable) -> AnexoSpec:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SpecError(f"no se pudo leer la especificación {path}: {exc}") from exc
    return parse_spec(data, origin=str(path))


class SpecRegistry:
    """All known spec versions, selectable by anexo and period."""

    def __init__(self, specs: list[AnexoSpec]) -> None:
        self._by_anexo: dict[int, list[AnexoSpec]] = {}
        seen_ids: set[str] = set()
        for spec in specs:
            if spec.spec_id in seen_ids:
                raise SpecError(f"spec_id repetido: {spec.spec_id}")
            seen_ids.add(spec.spec_id)
            self._by_anexo.setdefault(spec.anexo, []).append(spec)
        for anexo, items in self._by_anexo.items():
            items.sort(key=lambda s: parse_period(s.valid_from))
            for prev, nxt in zip(items, items[1:], strict=False):
                if prev.valid_to is None or parse_period(prev.valid_to) >= parse_period(nxt.valid_from):
                    raise SpecError(
                        f"las especificaciones {prev.spec_id} y {nxt.spec_id} del anexo {anexo} se traslapan"
                    )

    def for_period(self, anexo: int, year: int, month: int) -> AnexoSpec | None:
        for spec in self._by_anexo.get(anexo, []):
            if spec.covers(year, month):
                return spec
        return None

    def all(self) -> list[AnexoSpec]:
        return [spec for items in self._by_anexo.values() for spec in items]


def load_registry(directory: Path | Traversable | None = None) -> SpecRegistry:
    root = directory if directory is not None else resources.files("app.anexos").joinpath("specs")
    specs = [
        load_spec_file(entry)
        for entry in sorted(root.iterdir(), key=lambda e: e.name)
        if entry.is_file() and SPEC_FILE_GLOB.match(entry.name)
    ]
    if not specs:
        raise SpecError(f"no hay especificaciones en {root}")
    return SpecRegistry(specs)


@lru_cache(maxsize=1)
def default_registry() -> SpecRegistry:
    return load_registry()
