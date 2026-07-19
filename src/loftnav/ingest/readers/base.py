"""Reader-протокол: файл → один/несколько источников (Excel-лист = отдельный источник) [FR-002].

Каждый источник отдаёт поток записей dict[raw_col -> str|None]. Новый формат = новый reader-модуль
без правки диспетчера (диспетчер перебирает зарегистрированные ридеры по can_read).
"""

from __future__ import annotations

import datetime as _dt
import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass
class Source:
    suffix: str                       # "" для одиночного источника, имя листа для Excel
    records: Iterator                 # header != None => Iterator[list] (позиционно); иначе dict
    header: list[str | None] | None = None  # сырые имена колонок табличных форматов (по позиции)


class Reader(Protocol):
    @classmethod
    def can_read(cls, path: Path) -> bool: ...

    def sources(self, path: Path) -> Iterator[Source]: ...


def normalize_cell(value: object) -> str | None:
    """Значение ячейки → str|None. Вложенные структуры → JSON-строка (FR-004); пусто → None."""
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (_dt.date, _dt.datetime)):
        return value.isoformat()
    s = str(value)
    return s if s != "" else None
