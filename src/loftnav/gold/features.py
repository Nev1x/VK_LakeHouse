"""apartments_features (FR-004): row-level feature-таблица из silver — вход 006. Frozen-схема (I-6).

is_loft ВСЕГДА NULL (target-заготовка; эвристика style ILIKE '%loft%' ЗАПРЕЩЕНА — лже-таргет/утечка,
I-11). price_per_m2 NULL при area=0 (NULLIF); floor_ratio NULL при floors_total NULL/0.
photo_urls — passthrough (gold не парсит). Значения (snapshot_id, run_id) — bind-параметры.
"""

from __future__ import annotations

from loftnav.gold.marts import GOLD_NS, MartSQL, _silver_ref

FEATURES_NAME = "apartments_features"
FEATURES_TABLE = f"{GOLD_NS}.{FEATURES_NAME}"


def features_sql(run_id: str, snapshot: int | None) -> MartSQL:
    cols = [
        ("id", "id"),
        ("source", "source"),
        ("external_id", "external_id"),
        ("price_rub", "price_rub"),
        ("area_m2", "area_m2"),
        ("price_per_m2", "CAST(price_rub / NULLIF(area_m2, 0) AS DECIMAL(12,2))"),
        ("rooms", "rooms"),
        ("floor", "floor"),
        ("floors_total", "floors_total"),
        ("metro_minutes", "metro_minutes"),
        ("floor_ratio",
         "CASE WHEN floors_total IS NULL OR floors_total = 0 THEN NULL "
         "ELSE CAST(floor AS DOUBLE) / CAST(floors_total AS DOUBLE) END"),
        ("district", "district"),
        ("style", "style"),
        ("renovation_style", "renovation_style"),
        ("has_renovation", "has_renovation"),
        ("has_furniture", "has_furniture"),
        ("listed_at", "listed_at"),
        ("photo_urls", "photo_urls"),
        # target-заготовка: константа NULL, НИКАКИХ эвристик по style (лже-таргет запрещён)
        ("is_loft", "CAST(NULL AS BOOLEAN)"),
        ("_silver_snapshot_id", "CAST(? AS VARCHAR)"),
        ("_source_transform_run_id", "_transform_run_id"),
        ("_gold_run_id", "?"),
        ("_computed_at", "current_timestamp"),
    ]
    from loftnav.ident import quote_ident
    body = ", ".join(f"{expr} AS {quote_ident(name)}" for name, expr in cols)
    sql = f"SELECT {body} FROM {_silver_ref(snapshot)}"
    snapshot_str = "none" if snapshot is None else str(int(snapshot))
    return MartSQL(
        FEATURES_TABLE, FEATURES_NAME, tuple(n for n, _ in cols), sql, [snapshot_str, run_id],
    )
