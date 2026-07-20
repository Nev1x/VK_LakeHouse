"""Метаданные экспорта features (FR-002): snapshot-пин, явный список колонок, DESCRIBE, null_count.

Snapshot-пин переиспользует marts.snapshots_relation (не пишем заново). Чтение — только через Trino.
"""

from __future__ import annotations

from loftnav.gold.marts import snapshots_relation

FEATURES_TABLE = "iceberg.gold.apartments_features"
_FEATURES_SCHEMA = "iceberg.gold"
_FEATURES_NAME = "apartments_features"
FEATURES_SNAPSHOTS = snapshots_relation(_FEATURES_SCHEMA, _FEATURES_NAME)

# Явный frozen-список колонок (НЕ SELECT * — additive-колонка features не просочится молча).
FEATURES_COLUMNS: tuple[str, ...] = (
    "id", "source", "external_id",
    "price_rub", "area_m2", "price_per_m2",
    "rooms", "floor", "floors_total", "metro_minutes", "floor_ratio",
    "district", "style", "renovation_style",
    "has_renovation", "has_furniture",
    "listed_at", "photo_urls", "is_loft",
    "_silver_snapshot_id", "_source_transform_run_id", "_gold_run_id", "_computed_at",
)


def snapshot_id(conn) -> int | None:
    cur = conn.cursor()
    cur.execute(f"SELECT snapshot_id FROM {FEATURES_SNAPSHOTS} ORDER BY committed_at DESC LIMIT 1")
    rows = cur.fetchall()
    return int(rows[0][0]) if rows else None


def describe(conn) -> list[tuple[str, str]]:
    """[(колонка, trino-тип)] в порядке FEATURES_COLUMNS (для манифеста и pyarrow-схемы)."""
    cur = conn.cursor()
    cur.execute(f"DESCRIBE {FEATURES_TABLE}")
    types = {r[0]: r[1] for r in cur.fetchall()}
    return [(c, types[c]) for c in FEATURES_COLUMNS if c in types]


def is_loft_null_count(conn, snapshot: int | None) -> int:
    """Число NULL в is_loft — агрегатным запросом (не итерацией в Python). Всегда = row_count."""
    cur = conn.cursor()
    cur.execute(f"SELECT count_if(is_loft IS NULL) FROM {_ref(snapshot)}")
    return int(cur.fetchall()[0][0])


def select_sql(snapshot: int | None) -> str:
    cols = ", ".join(FEATURES_COLUMNS)
    return f"SELECT {cols} FROM {_ref(snapshot)} ORDER BY id"


def _ref(snapshot: int | None) -> str:
    if snapshot is None:
        return FEATURES_TABLE
    return f"{FEATURES_TABLE} FOR VERSION AS OF {int(snapshot)}"
