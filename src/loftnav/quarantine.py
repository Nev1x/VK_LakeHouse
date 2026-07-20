"""Quarantine отбракованных строк (FR-008/I-2: молча не дропаем). Общий для 002/003.

iceberg.quarantine.<layer>_<source>_rejects. Значения — bind-параметры; имена — санитизированы;
чанкование INSERT — общий байт-бюджетный хелпер chunked_insert (FR-013).
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass

from loftnav import chunked_insert
from loftnav.ident import quote_ident

QUARANTINE_NS = "iceberg.quarantine"

_COLUMNS = ["run_id", "source", "raw_record", "reason", "rejected_at", "layer"]


@dataclass
class Reject:
    raw_record: str      # JSON исходной записи as-is
    reason: str          # человекочитаемая причина


def rejects_table(layer: str, source: str) -> str:
    """Полное имя таблицы отбраковки (компоненты санитизированы вызывающим, тут — квотирование)."""
    name = f"{layer}_{source}_rejects"
    return f"{QUARANTINE_NS}.{quote_ident(name)}"


def _ensure_table(conn, table: str) -> None:
    cur = conn.cursor()
    cur.execute(
        f"CREATE TABLE IF NOT EXISTS {table} ("
        "run_id varchar, source varchar, raw_record varchar, reason varchar, "
        "rejected_at timestamp, layer varchar) WITH (format = 'PARQUET', format_version = 2)"
    )
    cur.fetchall()


def write_rejects(
    conn,
    run_id: str,
    source: str,
    layer: str,
    rejects: list[Reject],
    *,
    chunk_rows: int = 1000,
    chunk_bytes: int = 700_000,
) -> int:
    """Пишет отбракованные строки в quarantine-таблицу (byte-aware чанки, chunked_insert)."""
    if not rejects:
        return 0
    table = rejects_table(layer, source)
    _ensure_table(conn, table)
    now = _dt.datetime.now(_dt.UTC).replace(tzinfo=None)
    rows = [[run_id, source, r.raw_record, r.reason, now, layer] for r in rejects]
    written = 0
    base = chunked_insert.insert_prefix_len(table, _COLUMNS)
    for batch in chunked_insert.iter_byte_chunks(
        rows, chunk_rows=chunk_rows, chunk_bytes=chunk_bytes, base_len=base
    ):
        chunked_insert.insert_multi(conn, table, _COLUMNS, batch)
        written += len(batch)
    return written
