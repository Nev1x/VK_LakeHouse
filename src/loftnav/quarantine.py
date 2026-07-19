"""Quarantine отбракованных строк (FR-008, I-2: молча не дропаем). Общий для 002/003.

iceberg.quarantine.<layer>_<source>_rejects. Значения — bind-параметры; имена — санитизированы.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass

from loftnav.ingest.inference import quote_ident

QUARANTINE_NS = "iceberg.quarantine"


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
) -> int:
    """Пишет отбракованные строки в quarantine-таблицу слоя. Возвращает число записанных строк."""
    if not rejects:
        return 0
    table = rejects_table(layer, source)
    _ensure_table(conn, table)
    now = _dt.datetime.now(_dt.UTC).replace(tzinfo=None)
    cur = conn.cursor()
    written = 0
    for start in range(0, len(rejects), chunk_rows):
        batch = rejects[start : start + chunk_rows]
        placeholders = ",".join(["(?,?,?,?,?,?)"] * len(batch))
        params: list[object] = []
        for r in batch:
            params += [run_id, source, r.raw_record, r.reason, now, layer]
        cur.execute(
            f"INSERT INTO {table} (run_id, source, raw_record, reason, rejected_at, layer) "
            f"VALUES {placeholders}",
            params,
        )
        cur.fetchall()
        written += len(batch)
    return written
