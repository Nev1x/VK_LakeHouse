"""Декларативные mapping-конфиги источников (FR-002): TOML → валидированная модель + цепочка.

tomllib (stdlib, 0 новых зависимостей). Закрытый набор примитивов, НИКАКОГО eval/exec (I-7/I-14).
Строгая валидация при старте (fail fast). config_hash → в silver-строки и журнал (reprocess FR-008).
"""

from __future__ import annotations

import hashlib
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from loftnav.transform import normalize
from loftnav.transform.silver_writer import MAPPABLE_FIELDS

_ALLOWED_FIELD_KEYS = {
    "input", "regex_replace", "regex_extract", "enum_map", "unit_convert", "cast", "default",
}
_ALLOWED_CASTS = {"decimal", "bigint", "boolean", "timestamp", "varchar"}
_CASTS = {
    "decimal": normalize.cast_decimal,
    "bigint": normalize.cast_bigint,
    "boolean": normalize.cast_boolean,
    "timestamp": normalize.cast_timestamp,
    "varchar": str,
}


class MappingError(ValueError):
    """Ошибка конфигурации маппинга (fail fast при старте transform)."""


@dataclass
class FieldSpec:
    input: str | None = None
    regex_replace: tuple[str, str] | None = None   # (pattern, replacement)
    regex_extract: str | None = None               # pattern
    enum_map: dict[str, object] | None = None      # ключи casefold+trim
    unit_convert: tuple[str, str] | None = None    # (from, to)
    cast: str | None = None
    default: object | None = None

    def apply(self, raw: str | None, cap: int) -> object:
        """Применяет примитивы в фиксированном порядке; NormalizationError → строка в quarantine."""
        v: object = raw
        if isinstance(v, str) and self.regex_replace is not None:
            v = normalize.regex_replace(v, self.regex_replace[0], self.regex_replace[1], cap)
        if isinstance(v, str) and self.regex_extract is not None:
            v = normalize.regex_extract(v, self.regex_extract, cap)
        if v is not None and self.enum_map is not None:
            key = normalize.casefold_trim(str(v))
            if key not in self.enum_map:
                raise normalize.NormalizationError(f"enum_map: нет соответствия для {v!r}")
            v = self.enum_map[key]
        elif isinstance(v, str) and self.cast is not None:
            v = _CASTS[self.cast](v)
        if self.unit_convert is not None and isinstance(v, normalize.Decimal):
            v = normalize.unit_convert(v, self.unit_convert[0], self.unit_convert[1])
        if v is None and self.default is not None:
            v = self.default
        return v


@dataclass
class Mapping:
    source: str
    external_id_column: str | None
    fields: dict[str, FieldSpec]
    config_hash: str
    inputs: list[str] = field(default_factory=list)

    def input_columns(self) -> set[str]:
        cols = set(self.inputs)
        if self.external_id_column:
            cols.add(self.external_id_column)
        return cols


def _parse_field(name: str, raw: dict) -> FieldSpec:
    unknown = set(raw) - _ALLOWED_FIELD_KEYS
    if unknown:
        raise MappingError(f"поле {name}: неизвестные ключи {sorted(unknown)}")
    spec = FieldSpec(input=raw.get("input"), default=raw.get("default"))
    if "regex_replace" in raw:
        rr = raw["regex_replace"]
        if not isinstance(rr, dict) or "pattern" not in rr or "replacement" not in rr:
            raise MappingError(f"поле {name}: regex_replace требует pattern+replacement")
        spec.regex_replace = (str(rr["pattern"]), str(rr["replacement"]))
    if "regex_extract" in raw:
        re_ = raw["regex_extract"]
        pattern = re_["pattern"] if isinstance(re_, dict) else re_
        spec.regex_extract = str(pattern)
    if "enum_map" in raw:
        em = raw["enum_map"]
        if not isinstance(em, dict) or not em:
            raise MappingError(f"поле {name}: enum_map должен быть непустым словарём")
        spec.enum_map = {normalize.casefold_trim(str(k)): v for k, v in em.items()}
    if "unit_convert" in raw:
        uc = raw["unit_convert"]
        if not isinstance(uc, dict) or "from" not in uc or "to" not in uc:
            raise MappingError(f"поле {name}: unit_convert требует from+to")
        spec.unit_convert = (str(uc["from"]), str(uc["to"]))
    if "cast" in raw:
        if raw["cast"] not in _ALLOWED_CASTS:
            raise MappingError(f"поле {name}: cast={raw['cast']!r} не из {sorted(_ALLOWED_CASTS)}")
        spec.cast = raw["cast"]
    return spec


def load_mapping(path: Path) -> Mapping:
    """Читает и валидирует TOML-конфиг источника. tomllib.load в 'rb' (T3)."""
    try:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise MappingError(f"{path}: невалидный TOML — {exc}") from exc

    raw_fields = data.get("fields", {})
    if not raw_fields:
        raise MappingError(f"{path}: секция [fields] пуста или отсутствует")
    fields: dict[str, FieldSpec] = {}
    inputs: list[str] = []
    for name, raw in raw_fields.items():
        if name not in MAPPABLE_FIELDS:
            raise MappingError(
                f"{path}: неизвестное silver-поле {name!r} (см. {sorted(MAPPABLE_FIELDS)})"
            )
        spec = _parse_field(name, raw)
        fields[name] = spec
        if spec.input:
            inputs.append(spec.input)

    config_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    return Mapping(
        source=path.stem,
        external_id_column=data.get("meta", {}).get("external_id"),
        fields=fields,
        config_hash=config_hash,
        inputs=inputs,
    )


def validate_against_bronze(mapping: Mapping, bronze_columns: set[str]) -> list[str]:
    """Проверяет input-колонки против bronze-схемы; возвращает warnings по непокрытым колонкам."""
    for col in mapping.input_columns():
        if col not in bronze_columns:
            raise MappingError(
                f"источник {mapping.source}: колонка {col!r} из конфига отсутствует в bronze-схеме "
                f"({sorted(bronze_columns)})"
            )
    covered = mapping.input_columns()
    uncovered = sorted(c for c in bronze_columns if c not in covered and not c.startswith("_"))
    return [f"колонка bronze {c!r} не покрыта маппингом (игнорируется)" for c in uncovered]
