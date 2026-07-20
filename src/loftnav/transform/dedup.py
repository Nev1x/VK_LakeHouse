"""Идентичность и intra-source дедуп (FR-005). Cross-source дедуп — out of scope (к 006)."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable


def make_id(source: str, external_id: str) -> str:
    """sha256 стабильного identity. Length-prefix source — коллизие-устойчивость к ':' (аудит #15).

    Наивный f"{source}:{external_id}" даёт коллизию ('a','b:c') == ('a:b','c');
    префикс длины делает конкатенацию инъективной.
    """
    payload = f"{len(source)}:{source}:{external_id}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def dedup_latest(rows: Iterable[dict]) -> list[dict]:
    """Внутри источника оставляет по одной строке на external_id — с максимальным _ingested_at.

    MERGE в silver требует уникального ключа в батче; дедуп гарантирует это по всей партиции.
    """
    best: dict[str, dict] = {}
    for r in rows:
        eid = r["external_id"]
        prev = best.get(eid)
        if prev is None or r["_ingested_at"] > prev["_ingested_at"]:
            best[eid] = r
    return list(best.values())
