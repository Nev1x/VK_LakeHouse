"""Запись в iceberg.silver.apartments_clean (FR-003/FR-006) — DDL + MERGE (upsert) + reprocess.

Схема FROZEN (additive-only для 004/006). MERGE: точечный ACID-upsert по (source, external_id),
last-write-wins по _ingested_at (I-2/I-15, spike на Trino 483). Значения — bind-параметры;
идентификаторы — санитизированы+квотированы (ident); чанки — байтовый бюджет (chunked_insert).
"""

from __future__ import annotations

from loftnav import chunked_insert
from loftnav.ident import quote_ident

SILVER_TABLE = "iceberg.silver.apartments_clean"
SILVER_COLUMNS_VERSION = 1

# (имя, SQL-тип) — порядок фиксирован (frozen). Деньги/площадь — DECIMAL (точная арифметика 004).
_SCHEMA: tuple[tuple[str, str], ...] = (
    ("id", "varchar"),
    ("source", "varchar"),
    ("external_id", "varchar"),
    ("price_rub", "decimal(12,2)"),
    ("area_m2", "decimal(8,2)"),
    ("rooms", "bigint"),
    ("floor", "bigint"),
    ("floors_total", "bigint"),
    ("metro_minutes", "bigint"),
    ("address", "varchar"),
    ("district", "varchar"),
    ("style", "varchar"),
    ("renovation_style", "varchar"),
    ("has_renovation", "boolean"),
    ("has_furniture", "boolean"),
    ("photo_urls", "varchar"),
    ("listed_at", "timestamp"),
    ("_source_run_id", "varchar"),
    ("_source_content_hash", "varchar"),
    ("_mapping_config_hash", "varchar"),
    ("_ingested_at", "timestamp"),
    ("_transformed_at", "timestamp"),
    ("_transform_run_id", "varchar"),
)

ALL_COLUMNS: list[str] = [n for n, _ in _SCHEMA]
COLUMN_TYPES: dict[str, str] = dict(_SCHEMA)
KEY_COLUMNS: tuple[str, ...] = ("source", "external_id")

# Доменные поля, задаваемые mapping-конфигом (external_id — через [meta]; id/service — авто).
MAPPABLE_FIELDS: frozenset[str] = frozenset(
    {
        "price_rub", "area_m2", "rooms", "floor", "floors_total", "metro_minutes",
        "address", "district", "style", "renovation_style", "has_renovation",
        "has_furniture", "photo_urls", "listed_at",
    }
)


def ensure_table(conn) -> None:
    cols_sql = ", ".join(f"{quote_ident(n)} {t}" for n, t in _SCHEMA)
    cur = conn.cursor()
    cur.execute(
        f"CREATE TABLE IF NOT EXISTS {SILVER_TABLE} ({cols_sql}) "
        "WITH (format = 'PARQUET', format_version = 2, partitioning = ARRAY['source'])"
    )
    cur.fetchall()


def delete_source(conn, source: str) -> None:
    """Reprocess (FR-008, I-2 — явное действие оператора): удаляет партицию источника (bind)."""
    cur = conn.cursor()
    cur.execute(f"DELETE FROM {SILVER_TABLE} WHERE source = ?", [source])
    cur.fetchall()


def _merge_sql() -> tuple[str, str]:
    """(prefix, suffix) MERGE вокруг плейсхолдеров VALUES. Source типизирован через CAST (устойчиво
    к all-NULL колонкам — тип не выводится из литералов)."""
    n = len(ALL_COLUMNS)
    v_names = [f"c{i}" for i in range(n)]
    select_casts = ", ".join(
        f"CAST(v.{v_names[i]} AS {COLUMN_TYPES[name]}) AS {quote_ident(name)}"
        for i, name in enumerate(ALL_COLUMNS)
    )
    non_key = [c for c in ALL_COLUMNS if c not in KEY_COLUMNS]
    set_clause = ", ".join(f"{quote_ident(c)} = s.{quote_ident(c)}" for c in non_key)
    insert_cols = ", ".join(quote_ident(c) for c in ALL_COLUMNS)
    insert_vals = ", ".join(f"s.{quote_ident(c)}" for c in ALL_COLUMNS)
    prefix = f"MERGE INTO {SILVER_TABLE} t USING (SELECT {select_casts} FROM (VALUES "
    suffix = (
        f") AS v({', '.join(v_names)})) AS s "
        "ON t.source = ? AND t.source = s.source AND t.external_id = s.external_id "
        f"WHEN MATCHED AND s._ingested_at > t._ingested_at THEN UPDATE SET {set_clause} "
        f"WHEN NOT MATCHED THEN INSERT ({insert_cols}) VALUES ({insert_vals})"
    )
    return prefix, suffix


def merge_rows(conn, source: str, rows: list[dict], *, chunk_rows: int, chunk_bytes: int) -> int:
    """MERGE строк источника в silver чанками (байтовый бюджет). Отдаёт число вмерженных строк."""
    if not rows:
        return 0
    ensure_table(conn)
    prefix, suffix = _merge_sql()
    n = len(ALL_COLUMNS)
    row_ph = "(" + ",".join(["?"] * n) + ")"
    positional = [[r.get(c) for c in ALL_COLUMNS] for r in rows]
    # база бюджета: статические prefix+suffix + запас на bind source-предиката
    base = len(prefix) + len(suffix) + 2 * len(source) + 8
    cur = conn.cursor()
    merged = 0
    for batch in chunked_insert.iter_byte_chunks(
        positional, chunk_rows=chunk_rows, chunk_bytes=chunk_bytes, base_len=base
    ):
        placeholders = ",".join([row_ph] * len(batch))
        params: list[object] = []
        for r in batch:
            params.extend(r)
        params.append(source)  # статический предикат ON t.source = ? — последний параметр
        cur.execute(prefix + placeholders + suffix, params)
        cur.fetchall()
        merged += len(batch)
    return merged
