"""Запись в iceberg.silver.apartments_clean (FR-003/FR-006) — DDL + MERGE (upsert) + reprocess.

Схема FROZEN (additive-only для 004/006). MERGE: точечный ACID-upsert по (source, external_id),
last-write-wins по _ingested_at (I-2/I-15, spike на Trino 483). Значения — bind-параметры;
идентификаторы — санитизированы+квотированы (ident); чанки — байтовый бюджет (chunked_insert).
"""

from __future__ import annotations

from loftnav import chunked_insert
from loftnav.ident import quote_ident

SILVER_TABLE = "iceberg.silver.apartments_clean"
SILVER_COLUMNS_VERSION = 2  # 007: +ceiling_height_m/wall_material/year_built (additive)

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
    # лофт-маркеры 007 (additive, nullable): источник без поля → NULL (напр. apartments_lite)
    ("ceiling_height_m", "decimal(4,2)"),
    ("wall_material", "varchar"),
    ("year_built", "bigint"),
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
        "ceiling_height_m", "wall_material", "year_built",   # лофт-маркеры 007
    }
)


def _describe_columns(conn, table: str) -> set[str]:
    """Существующие имена колонок таблицы через DESCRIBE ({} если таблицы нет)."""
    cur = conn.cursor()
    cur.execute(f"DESCRIBE {table}")
    return {r[0] for r in cur.fetchall()}


def _evolve_columns(conn, table: str, schema: tuple[tuple[str, str], ...]) -> list[str]:
    """Additive-эволюция схемы (I-6/I-10, образец bronze_writer.ensure_table): DESCRIBE → diff со
    `schema` → ALTER TABLE ADD COLUMN на КАЖДУЮ отсутствующую (nullable, в порядке schema).

    Идемпотентно: колонка уже есть → пропуск (повтор = no-op). Возвращает добавленные имена.
    Без этого пополнение `_SCHEMA` дало бы MERGE с INSERT на несуществующие колонки — падение ВСЕХ
    источников (CRITICAL-1 аудита 007).
    """
    existing = _describe_columns(conn, table)
    cur = conn.cursor()
    added: list[str] = []
    for name, typ in schema:
        if name in existing:
            continue
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {quote_ident(name)} {typ}")
        cur.fetchall()
        added.append(name)
    return added


def ensure_table(conn) -> None:
    """Создаёт silver-таблицу (fresh) или доэволюционирует её схему до `_SCHEMA` (additive).

    CREATE IF NOT EXISTS покрывает fresh-случай полной схемой; для уже существующей таблицы
    (в т.ч. со старым, более узким контрактом) недостающие колонки докатываются ALTER-ом.
    """
    cols_sql = ", ".join(f"{quote_ident(n)} {t}" for n, t in _SCHEMA)
    cur = conn.cursor()
    cur.execute(
        f"CREATE TABLE IF NOT EXISTS {SILVER_TABLE} ({cols_sql}) "
        "WITH (format = 'PARQUET', format_version = 2, partitioning = ARRAY['source'])"
    )
    cur.fetchall()
    _evolve_columns(conn, SILVER_TABLE, _SCHEMA)


def delete_source(conn, source: str) -> None:
    """Reprocess (FR-008, I-2 — явное действие оператора): удаляет партицию источника (bind)."""
    cur = conn.cursor()
    cur.execute(f"DELETE FROM {SILVER_TABLE} WHERE source = ?", [source])
    cur.fetchall()


def _merge_sql(
    table: str,
    columns: list[str],
    column_types: dict[str, str],
    key_columns: tuple[str, ...],
) -> tuple[str, str]:
    """(prefix, suffix) MERGE вокруг плейсхолдеров VALUES. Source типизирован через CAST (устойчиво
    к all-NULL колонкам — тип не выводится из литералов). Параметризован таблицей/колонками, чтобы
    один и тот же путь записи проверялся гвард-тестами на расширенной схеме (007)."""
    n = len(columns)
    v_names = [f"c{i}" for i in range(n)]
    select_casts = ", ".join(
        f"CAST(v.{v_names[i]} AS {column_types[name]}) AS {quote_ident(name)}"
        for i, name in enumerate(columns)
    )
    non_key = [c for c in columns if c not in key_columns]
    set_clause = ", ".join(f"{quote_ident(c)} = s.{quote_ident(c)}" for c in non_key)
    insert_cols = ", ".join(quote_ident(c) for c in columns)
    insert_vals = ", ".join(f"s.{quote_ident(c)}" for c in columns)
    prefix = f"MERGE INTO {table} t USING (SELECT {select_casts} FROM (VALUES "
    suffix = (
        f") AS v({', '.join(v_names)})) AS s "
        "ON t.source = ? AND t.source = s.source AND t.external_id = s.external_id "
        f"WHEN MATCHED AND s._ingested_at > t._ingested_at THEN UPDATE SET {set_clause} "
        f"WHEN NOT MATCHED THEN INSERT ({insert_cols}) VALUES ({insert_vals})"
    )
    return prefix, suffix


def _merge_into(
    conn,
    table: str,
    columns: list[str],
    column_types: dict[str, str],
    key_columns: tuple[str, ...],
    source: str,
    rows: list[dict],
    *,
    chunk_rows: int,
    chunk_bytes: int,
) -> int:
    """MERGE строк источника в `table` чанками (байтовый бюджет). Отдаёт число вмерженных строк."""
    if not rows:
        return 0
    prefix, suffix = _merge_sql(table, columns, column_types, key_columns)
    n = len(columns)
    row_ph = "(" + ",".join(["?"] * n) + ")"
    positional = [[r.get(c) for c in columns] for r in rows]
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


def merge_rows(conn, source: str, rows: list[dict], *, chunk_rows: int, chunk_bytes: int) -> int:
    """MERGE строк источника в silver чанками (байтовый бюджет). Отдаёт число вмерженных строк.

    ensure_table доэволюционирует схему ДО записи — INSERT никогда не ссылается на несуществующую
    колонку при расширении `_SCHEMA` (CRITICAL-1 аудита 007)."""
    if not rows:
        return 0
    ensure_table(conn)
    return _merge_into(
        conn, SILVER_TABLE, ALL_COLUMNS, COLUMN_TYPES, KEY_COLUMNS, source, rows,
        chunk_rows=chunk_rows, chunk_bytes=chunk_bytes,
    )
