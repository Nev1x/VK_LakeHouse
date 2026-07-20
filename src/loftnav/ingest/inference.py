"""Schema inference примитивов Iceberg (FR-003, FR-004) + реэкспорт санитайзера идентификаторов.

Санитизация/квотирование идентификаторов вынесены в нейтральный `loftnav.ident` (FR-013 003);
здесь реэкспортируются для обратной совместимости 002. Значения — только bind-параметры.
"""

from __future__ import annotations

import datetime as _dt
import re
from collections.abc import Iterable

# Реэкспорт (совместимость 002): единая точка санитизации — loftnav.ident.
from loftnav.ident import quote_ident, sanitize_columns, sanitize_identifier

__all__ = [
    "coerce_value",
    "infer_type",
    "quote_ident",
    "sanitize_columns",
    "sanitize_identifier",
]

# Типы-примитивы Iceberg, которые выводит inference (FR-004).
TYPE_VARCHAR = "VARCHAR"
TYPE_BIGINT = "BIGINT"
TYPE_DOUBLE = "DOUBLE"
TYPE_BOOLEAN = "BOOLEAN"
TYPE_DATE = "DATE"
TYPE_TIMESTAMP = "TIMESTAMP"

_INT_RE = re.compile(r"^[+-]?\d+$")
_INT64_MIN, _INT64_MAX = -(2**63), 2**63 - 1
_BOOL_TRUE = {"true", "t", "yes"}
_BOOL_FALSE = {"false", "f", "no"}


# --- inference значений ---


def _is_int(v: str) -> bool:
    if not _INT_RE.match(v):
        return False
    try:
        return _INT64_MIN <= int(v) <= _INT64_MAX
    except ValueError:
        return False


def _is_float(v: str) -> bool:
    # запятая-десятичная остаётся VARCHAR (без магии — FR-004)
    if "," in v:
        return False
    try:
        float(v)
        return v.strip().lower() not in ("inf", "-inf", "nan", "+inf")
    except ValueError:
        return False


def _is_bool(v: str) -> bool:
    return v.lower() in _BOOL_TRUE or v.lower() in _BOOL_FALSE


def _is_date(v: str) -> bool:
    try:
        _dt.date.fromisoformat(v)
        return True
    except ValueError:
        return False


def _is_timestamp(v: str) -> bool:
    try:
        _dt.datetime.fromisoformat(v)
        return True
    except ValueError:
        return False


def infer_type(values: Iterable[str | None]) -> str:
    """Тип колонки по её значениям. Пустая колонка / конфликт → VARCHAR (FR-004)."""
    non_null = [v for v in values if v is not None and v != ""]
    if not non_null:
        return TYPE_VARCHAR
    for typ, pred in (
        (TYPE_BOOLEAN, _is_bool),
        (TYPE_BIGINT, _is_int),
        (TYPE_DOUBLE, _is_float),
        (TYPE_DATE, _is_date),
        (TYPE_TIMESTAMP, _is_timestamp),
    ):
        if all(pred(v) for v in non_null):
            return typ
    return TYPE_VARCHAR


def coerce_value(raw: str | None, typ: str):
    """Сырое значение → python-объект под bind-параметр Trino. Ошибка → ValueError (в reject)."""
    if raw is None or raw == "":
        return None
    if typ == TYPE_BIGINT:
        if not _is_int(raw):
            raise ValueError(f"не BIGINT: {raw!r}")
        return int(raw)
    if typ == TYPE_DOUBLE:
        if not _is_float(raw):
            raise ValueError(f"не DOUBLE: {raw!r}")
        return float(raw)
    if typ == TYPE_BOOLEAN:
        low = raw.lower()
        if low in _BOOL_TRUE:
            return True
        if low in _BOOL_FALSE:
            return False
        raise ValueError(f"не BOOLEAN: {raw!r}")
    if typ == TYPE_DATE:
        return _dt.date.fromisoformat(raw)
    if typ == TYPE_TIMESTAMP:
        return _dt.datetime.fromisoformat(raw)
    return str(raw)
