"""Санитизация и квотирование идентификаторов SQL (I-7) — нейтральный общий модуль (FR-013).

ЕДИНАЯ точка для ВСЕХ имён (источник, листы, колонки bronze, поля silver). Ни один идентификатор
не попадает в текст SQL, минуя эти функции; значения — только bind-параметры.
Реэкспортируется из ingest/inference для обратной совместимости 002.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

# Служебный префикс `_` зарезервирован (FR-006). Пользовательские имена с ним → `u_...` (FR-003).
_ALLOWED_RE = re.compile(r"[^a-z0-9_]")
_VALID_RE = re.compile(r"[a-z0-9_]+")


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
    if not _VALID_RE.fullmatch(name):
        raise ValueError(f"несанитизированный идентификатор в SQL: {name!r}")
    return '"' + name + '"'
