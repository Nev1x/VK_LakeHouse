"""Запись в iceberg.bronze.<source> через Trino (FR-006/FR-007/FR-010).

Только параметризованный SQL: значения — bind-параметры, идентификаторы санитизированы+квотированы.
Прямая запись parquet в warehouse ЗАПРЕЩЕНА (I-4). DDL: format_version=2 (row-level DELETE).
"""

from __future__ import annotations

import datetime as _dt
from collections.abc import Iterable

from loftnav.ingest.inference import quote_ident

BRONZE_NS = "iceberg.bronze"

# Служебные колонки (`_`-префикс зарезервирован — FR-006).
SERVICE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("_run_id", "varchar"),
    ("_content_hash", "varchar"),
    ("_source_file", "varchar"),
    ("_ingested_at", "timestamp"),
)

# Разрешённые additive-промоции типов (FR-007).
_PROMOTIONS = {
    ("BIGINT", "DOUBLE"),
    ("INTEGER", "BIGINT"),
    ("INTEGER", "DOUBLE"),
    ("REAL", "DOUBLE"),
}


class SchemaConflict(Exception):
    """Несовместимый тип существующей колонки → файл failed (FR-007, I-6)."""


def resolve_column_type(existing: str, new: str) -> str:
    """Эффективный тип существующей колонки при повторной загрузке (FR-007).

    Равные типы / разрешённая промоция в любую сторону → существующий тип (авторитетен, additive);
    иначе SchemaConflict (никакого auto-widening несовместимых типов).
    """
    existing, new = existing.upper(), new.upper()
    if new == existing:
        return existing
    if (existing, new) in _PROMOTIONS or (new, existing) in _PROMOTIONS:
        return existing
    raise SchemaConflict(f"несовместимый тип {new} с существующим {existing}")


def bronze_table(source: str) -> str:
    return f"{BRONZE_NS}.{quote_ident(source)}"


def _existing_schema(conn, source: str) -> dict[str, str]:
    """Существующие data-колонки (без служебных) и их типы (UPPER). {} если таблицы нет."""
    cur = conn.cursor()
    cur.execute(
        "SELECT column_name, data_type FROM iceberg.information_schema.columns "
        "WHERE table_schema = 'bronze' AND table_name = ?",
        [source],
    )
    out: dict[str, str] = {}
    for name, dtype in cur.fetchall():
        if name.startswith("_"):
            continue
        out[name] = _normalize_type(dtype)
    return out


def _normalize_type(dtype: str) -> str:
    base = dtype.split("(", 1)[0].strip().upper()
    return base


def ensure_table(conn, source: str, data_schema: dict[str, str]) -> dict[str, str]:
    """Создаёт/эволюционирует bronze-таблицу; возвращает ЭФФЕКТИВНУЮ схему (типы в таблице).

    Новая таблица → CREATE с data + служебными колонками. Существующая → ALTER ADD COLUMN для новых
    (nullable, additive); конфликт типа существующей колонки вне промоций → SchemaConflict (FR-007).
    """
    table = bronze_table(source)
    existing = _existing_schema(conn, source)
    cur = conn.cursor()

    if not existing:
        cols_sql = ", ".join(
            f"{quote_ident(c)} {t}" for c, t in data_schema.items()
        )
        service_sql = ", ".join(f"{quote_ident(c)} {t}" for c, t in SERVICE_COLUMNS)
        sep = ", " if cols_sql else ""
        cur.execute(
            f"CREATE TABLE IF NOT EXISTS {table} ({cols_sql}{sep}{service_sql}) "
            "WITH (format = 'PARQUET', format_version = 2)"
        )
        cur.fetchall()
        return dict(data_schema)

    effective = dict(existing)
    for col, new_type in data_schema.items():
        if col not in existing:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {quote_ident(col)} {new_type}")
            cur.fetchall()
            effective[col] = new_type
            continue
        # существующая колонка авторитетна; конфликт вне промоций → SchemaConflict (файл failed)
        effective[col] = resolve_column_type(existing[col], new_type)
    return effective


def delete_by_content_hash(conn, source: str, content_hash: str) -> None:
    """Replay: удаляет ТОЛЬКО строки этого файла (FR-010, I-2; bind-параметр, fv2 row-level)."""
    cur = conn.cursor()
    cur.execute(
        f"DELETE FROM {bronze_table(source)} WHERE _content_hash = ?",
        [content_hash],
    )
    cur.fetchall()


def insert_prefix_len(source: str, columns: list[str]) -> int:
    """Длина статического префикса INSERT (учитывается в бюджете длины запроса)."""
    col_sql = ", ".join(quote_ident(c) for c in columns)
    return len(f"INSERT INTO {bronze_table(source)} ({col_sql}) VALUES ")


def estimate_row_sql(row: Iterable[object]) -> int:
    """Оценка ДЛИНЫ ИНЛАЙНОВОГО литерала строки в тексте запроса (trino инлайнит params).

    Консервативно (over-estimate): строки — с worst-case экранированием кавычек (×2) и обрамлением;
    типизированные литералы (timestamp/date) — с запасом. CRITICAL-2: чанк режем по этой оценке.
    """
    total = 2  # ()
    for v in row:
        if v is None:
            total += 4                         # NULL
        elif isinstance(v, bool):
            total += 5
        elif isinstance(v, str):
            total += 2 * len(v) + 3            # кавычки + worst-case экранирование
        elif isinstance(v, (_dt.datetime, _dt.date)):
            total += 40                        # TIMESTAMP '....' / DATE '....'
        else:
            total += len(str(v)) + 2
        total += 1                             # запятая
    return total


def insert_batch(conn, source: str, columns: list[str], batch: list[list]) -> None:
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
    cur.execute(f"INSERT INTO {bronze_table(source)} ({col_sql}) VALUES {placeholders}", params)
    cur.fetchall()
