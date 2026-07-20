"""Общий байт-бюджетный multi-row хелпер (FR-013): estimate/prefix/chunk/insert.

trino инлайнит bind-параметры в текст запроса (query.max-length=1_000_000 символов) — чанки режутся
по ОЦЕНКЕ ДЛИНЫ ТЕКСТА, не по размеру значений. Используют bronze_writer, quarantine, silver_writer.
Значения — только bind-параметры; имена — санитизированы+квотированы (loftnav.ident).
"""

from __future__ import annotations

import datetime as _dt
from collections.abc import Iterable, Iterator

from loftnav.ident import quote_ident


def estimate_row_sql(row: Iterable[object]) -> int:
    """Оценка ДЛИНЫ инлайнового литерала строки в тексте запроса (консервативно, over-estimate).

    Строки — worst-case экранирование кавычек (×2) + обрамление; typed-литералы (timestamp/date)
    — с запасом. По этой оценке режутся чанки INSERT/MERGE (CRITICAL-2 урока 002).
    """
    total = 2  # ()
    for v in row:
        if v is None:
            total += 4
        elif isinstance(v, bool):
            total += 5
        elif isinstance(v, str):
            total += 2 * len(v) + 3
        elif isinstance(v, (_dt.datetime, _dt.date)):
            total += 40
        else:
            total += len(str(v)) + 2
        total += 1
    return total


def insert_prefix_len(table: str, columns: list[str]) -> int:
    """Длина статического префикса INSERT (учитывается в бюджете длины запроса)."""
    col_sql = ", ".join(quote_ident(c) for c in columns)
    return len(f"INSERT INTO {table} ({col_sql}) VALUES ")


def iter_byte_chunks(
    rows: Iterable[list],
    *,
    chunk_rows: int,
    chunk_bytes: int,
    base_len: int = 0,
) -> Iterator[list[list]]:
    """Режет поток строк на батчи ≤chunk_rows и с суммарной оценкой текста ≤chunk_bytes."""
    batch: list[list] = []
    size = base_len
    for r in rows:
        est = estimate_row_sql(r)
        if batch and (len(batch) >= chunk_rows or size + est > chunk_bytes):
            yield batch
            batch, size = [], base_len
        batch.append(r)
        size += est
    if batch:
        yield batch


def insert_multi(conn, table: str, columns: list[str], batch: list[list]) -> None:
    """Один multi-row параметризованный INSERT для переданного батча (значения — bind-параметры)."""
    if not batch:
        return
    col_sql = ", ".join(quote_ident(c) for c in columns)
    row_ph = "(" + ",".join(["?"] * len(columns)) + ")"
    placeholders = ",".join([row_ph] * len(batch))
    params: list[object] = []
    for r in batch:
        params.extend(r)
    cur = conn.cursor()
    cur.execute(f"INSERT INTO {table} ({col_sql}) VALUES {placeholders}", params)
    cur.fetchall()
