"""Юнит-тесты SQL витрин (FR-002/FR-003): нет SELECT *, явные колонки, snapshot-пин, NULLIF."""

from __future__ import annotations

import pytest

from loftnav.gold import marts

_RID = "a" * 32
_SNAP = 123456789


def _all_marts():
    return [b(_RID, 3, _SNAP) for b in marts.MARTS.values()]


def test_snapshots_relation_exact() -> None:
    # $snapshots строится ОТДЕЛЬНОЙ функцией, не через ident (T2)
    assert marts.snapshots_relation("iceberg.silver", "apartments_clean") == (
        'iceberg.silver."apartments_clean$snapshots"'
    )
    assert marts.SILVER_SNAPSHOTS == 'iceberg.silver."apartments_clean$snapshots"'


@pytest.mark.parametrize("mart", _all_marts(), ids=lambda m: m.name)
def test_no_select_star(mart) -> None:
    low = mart.select_sql.lower()
    assert "select *" not in low        # явный список колонок (count(*) допустим)
    assert " * from" not in low


@pytest.mark.parametrize("mart", _all_marts(), ids=lambda m: m.name)
def test_snapshot_pinned(mart) -> None:
    assert f"FOR VERSION AS OF {_SNAP}" in mart.select_sql   # детерминизм (NFR-004)


def test_district_mart_columns_and_median() -> None:
    m = marts.mart_price_area_by_district(_RID, 3, _SNAP)
    assert m.columns == (
        "district", "listing_count", "avg_price_rub", "median_price_rub",
        "min_price_rub", "max_price_rub", "avg_price_per_m2", "avg_area_m2",
        "_computed_at", "_gold_run_id",
    )
    # медиана — ТОЧНАЯ (array_agg+ORDER BY), детерминизм NFR-004; НЕ approx_percentile
    assert "array_agg(CAST(price_rub AS DOUBLE) ORDER BY price_rub)" in m.select_sql
    assert "FILTER (WHERE price_rub IS NOT NULL)" in m.select_sql   # NULL-цены игнорируются
    assert "approx_percentile" not in m.select_sql
    assert "AS DECIMAL(12,2))" in m.select_sql
    # деление на ноль защищено NULLIF
    assert "NULLIF(area_m2, 0)" in m.select_sql
    assert m.params == [_RID]


@pytest.mark.parametrize("mart", _all_marts(), ids=lambda m: m.name)
def test_no_approx_percentile_regression(mart) -> None:
    """Guard (root cause 2026-07-22): недетерминированный approx_percentile запрещён в витринах."""
    assert "approx_percentile" not in mart.select_sql


def test_style_mart_small_sample_param_order() -> None:
    m = marts.mart_style_renovation_furniture(_RID, 3, _SNAP)
    assert "count(*) < ?" in m.select_sql
    assert "lower(trim(style))" in m.select_sql   # нормализация (FR-007)
    assert m.params == [3, _RID]                   # порог, затем run_id (порядок '?')


def test_dynamics_no_gaps_and_cumulative() -> None:
    m = marts.mart_listing_dynamics(_RID, 3, _SNAP)
    assert "sequence(b.mn, b.mx, INTERVAL '1' DAY)" in m.select_sql   # date-spine (нет дыр)
    assert "OVER (ORDER BY spine.load_date)" in m.select_sql           # cumulative
    assert "WHERE b.mn IS NOT NULL" in m.select_sql                    # пустой silver safe
    assert m.params == [_RID]


def test_none_snapshot_no_time_travel() -> None:
    m = marts.mart_price_area_by_district(_RID, 3, None)
    assert "FOR VERSION AS OF" not in m.select_sql   # None => текущее состояние
