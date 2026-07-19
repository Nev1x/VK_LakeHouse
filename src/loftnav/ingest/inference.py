"""Санитизация идентификаторов (I-7) и schema inference примитивов Iceberg (FR-003, FR-004).

sanitize_identifier — ЕДИНАЯ функция для ВСЕХ имён (источник, листы, колонки). Ни один
идентификатор не попадает в текст SQL, минуя её. Значения при этом идут только bind-параметрами;
идентификаторы дополнительно двойными кавычками (`quote_ident`).
"""

from __future__ import annotations

import datetime as _dt
import re
from collections.abc import Iterable

# Служебный префикс `_` зарезервирован (FR-006). Пользовательские имена с ним → `u_...` (FR-003).
_ALLOWED_RE = re.compile(r"[^a-z0-9_]")

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


def sanitize_identifier(name: str) -> str:
    """Имя → безопасный идентификатор `[a-z0-9_]` (I-7). Пусто → '' (caller даст col_N)."""
    s = (name or "").strip().lower()
    s = _ALLOWED_RE.sub("_", s)          # не-ASCII и запрещённые символы → _
    if not s or s.strip("_") == "":       # пусто/только подчёркивания
        return ""
    if s[0].isdigit():                    # не начинается с цифры
        s = f"c_{s}"
    elif s.startswith("_"):               # пользовательский _-префикс зарезервирован → u_
        s = f"u{s}"
    return s


def sanitize_columns(raw_names: Iterable[str]) -> list[str]:
    """Список сырых имён → санитизированные с дедупликацией (`_2`, `_3`, ...) и col_N для пустых."""
    used: set[str] = set()
    out: list[str] = []
    for i, raw in enumerate(raw_names):
        base = sanitize_identifier(raw) or f"col_{i}"
        cand, k = base, 2
        while cand in used:
            cand = f"{base}_{k}"
            k += 1
        used.add(cand)
        out.append(cand)
    return out


def quote_ident(name: str) -> str:
    """Двойное квотирование идентификатора для SQL (имя уже санитизировано)."""
    if not re.fullmatch(r"[a-z0-9_]+", name):
        raise ValueError(f"несанитизированный идентификатор в SQL: {name!r}")
    return '"' + name + '"'


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
