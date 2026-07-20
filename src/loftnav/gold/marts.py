"""Определения gold-витрин как код (FR-002/FR-003): tuple-driven, ЯВНЫЕ колонки (НЕ SELECT *).

Витрины frozen (I-6): набор курируется, additive-only. Медиана — approx_percentile(CAST DOUBLE,0.5)
с явным CAST обратно в DECIMAL. Каждая агрегатная колонка — явный CAST(p,s), не вывод CTAS.
Значения (run_id, порог) — bind-параметры; идентификаторы-алиасы — ident.quote_ident.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from loftnav.ident import quote_ident

SILVER = "iceberg.silver.apartments_clean"
_SILVER_SCHEMA = "iceberg.silver"
_SILVER_TABLE = "apartments_clean"
GOLD_NS = "iceberg.gold"
GOLD_COLUMNS_VERSION = 1


def snapshots_relation(schema: str, table: str) -> str:
    """metadata-таблица $snapshots: '$' отклоняется ident/quote_ident — квотируем ОТДЕЛЬНО (T2).

    ident.py НЕ трогаем; имя базовой таблицы — frozen-константа, санитизация не нужна.
    """
    return f'{schema}."{table}$snapshots"'


SILVER_SNAPSHOTS = snapshots_relation(_SILVER_SCHEMA, _SILVER_TABLE)


def _silver_ref(snapshot_id: int | None) -> str:
    """FROM-ссылка на silver, пиненная на snapshot (детерминизм NFR-004).

    snapshot_id — bigint из $snapshots (валидируется как int в run.py) => безопасен как литерал.
    None (нет снапшота) => читаем текущее состояние.
    """
    if snapshot_id is None:
        return SILVER
    return f"{SILVER} FOR VERSION AS OF {int(snapshot_id)}"


@dataclass
class MartSQL:
    target: str               # полное имя витрины iceberg.gold.<name>
    name: str
    columns: tuple[str, ...]
    select_sql: str           # SELECT ... с '?' плейсхолдерами
    params: list              # bind-параметры в порядке появления '?'


def _select(cols: list[tuple[str, str]], from_group: str) -> str:
    body = ", ".join(f"{expr} AS {quote_ident(name)}" for name, expr in cols)
    return f"SELECT {body} {from_group}"


def mart_price_area_by_district(run_id: str, small_sample: int, snapshot: int | None) -> MartSQL:
    cols = [
        ("district", "COALESCE(district, 'unknown')"),
        ("listing_count", "CAST(count(*) AS BIGINT)"),
        ("avg_price_rub", "CAST(avg(price_rub) AS DECIMAL(12,2))"),
        ("median_price_rub",
         "CAST(approx_percentile(CAST(price_rub AS DOUBLE), 0.5) AS DECIMAL(12,2))"),
        ("min_price_rub", "CAST(min(price_rub) AS DECIMAL(12,2))"),
        ("max_price_rub", "CAST(max(price_rub) AS DECIMAL(12,2))"),
        ("avg_price_per_m2", "CAST(avg(price_rub / NULLIF(area_m2, 0)) AS DECIMAL(12,2))"),
        ("avg_area_m2", "CAST(avg(area_m2) AS DECIMAL(8,2))"),
        ("_computed_at", "current_timestamp"),
        ("_gold_run_id", "?"),
    ]
    from_group = f"FROM {_silver_ref(snapshot)} GROUP BY COALESCE(district, 'unknown')"
    return MartSQL(
        f"{GOLD_NS}.mart_price_area_by_district", "mart_price_area_by_district",
        tuple(n for n, _ in cols), _select(cols, from_group), [run_id],
    )


def mart_style_renovation_furniture(
    run_id: str, small_sample: int, snapshot: int | None
) -> MartSQL:
    style = "COALESCE(lower(trim(style)), 'none')"
    reno = "COALESCE(lower(trim(renovation_style)), 'none')"
    cols = [
        ("style_norm", style),
        ("renovation_style_norm", reno),
        ("has_renovation", "has_renovation"),
        ("has_furniture", "has_furniture"),
        ("listing_count", "CAST(count(*) AS BIGINT)"),
        ("avg_price_rub", "CAST(avg(price_rub) AS DECIMAL(12,2))"),
        ("median_price_rub",
         "CAST(approx_percentile(CAST(price_rub AS DOUBLE), 0.5) AS DECIMAL(12,2))"),
        ("avg_area_m2", "CAST(avg(area_m2) AS DECIMAL(8,2))"),
        ("is_small_sample", "count(*) < ?"),
        ("_computed_at", "current_timestamp"),
        ("_gold_run_id", "?"),
    ]
    from_group = (
        f"FROM {_silver_ref(snapshot)} "
        f"GROUP BY {style}, {reno}, has_renovation, has_furniture"
    )
    return MartSQL(
        f"{GOLD_NS}.mart_style_renovation_furniture", "mart_style_renovation_furniture",
        tuple(n for n, _ in cols), _select(cols, from_group), [small_sample, run_id],
    )


def mart_listing_dynamics(run_id: str, small_sample: int, snapshot: int | None) -> MartSQL:
    ref = _silver_ref(snapshot)
    columns = ("load_date", "listings_added", "listings_added_cumulative",
               "_computed_at", "_gold_run_id")
    # daily + cumulative по DATE(_ingested_at); date-spine убирает дыры в ряду (US-3);
    # WHERE mn IS NOT NULL => пустой silver даёт пустую витрину без ошибки sequence(NULL)
    sql = (
        "WITH b AS (SELECT min(DATE(_ingested_at)) AS mn, "
        f"max(DATE(_ingested_at)) AS mx FROM {ref}), "
        "spine AS (SELECT d AS load_date FROM b "
        "CROSS JOIN UNNEST(sequence(b.mn, b.mx, INTERVAL '1' DAY)) AS t(d) "
        "WHERE b.mn IS NOT NULL), "
        f"daily AS (SELECT DATE(_ingested_at) AS load_date, count(*) AS c FROM {ref} "
        "GROUP BY DATE(_ingested_at)) "
        "SELECT spine.load_date AS load_date, "
        "CAST(COALESCE(daily.c, 0) AS BIGINT) AS listings_added, "
        "CAST(sum(COALESCE(daily.c, 0)) OVER (ORDER BY spine.load_date) AS BIGINT) "
        "AS listings_added_cumulative, "
        "current_timestamp AS _computed_at, ? AS _gold_run_id "
        "FROM spine LEFT JOIN daily ON spine.load_date = daily.load_date"
    )
    return MartSQL(
        f"{GOLD_NS}.mart_listing_dynamics", "mart_listing_dynamics", columns, sql, [run_id],
    )


MartBuilder = Callable[[str, int, "int | None"], MartSQL]

MARTS: dict[str, MartBuilder] = {
    "mart_price_area_by_district": mart_price_area_by_district,
    "mart_style_renovation_furniture": mart_style_renovation_furniture,
    "mart_listing_dynamics": mart_listing_dynamics,
}
