"""Интеграционные тесты build-gold на живом стеке (FR-005..FR-010, FR-012). Маркер requires_stack.

Требуют непустой silver (make transform-demo). Балансы, стабильность схемы, детерминизм,
пустой silver, защитные NULL, атомарный swap при чтении.
"""

from __future__ import annotations

import threading
import uuid

import pytest

from loftnav.config import GoldConfig
from loftnav.gold import features, marts
from loftnav.gold.run import EXIT_OK, run_build_gold
from loftnav.trino_client import get_connection

pytestmark = pytest.mark.requires_stack


def _q(sql: str, params=None):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, params) if params is not None else cur.execute(sql)
        return cur.fetchall()
    finally:
        conn.close()


def _gcfg() -> GoldConfig:
    return GoldConfig.from_env()


# копия схемы silver в пустую temp-таблицу (SELECT * здесь намеренно — переносим весь набор колонок)
_EMPTY_LIKE = "AS SELECT * FROM iceberg.silver.apartments_clean WHERE 1=0"


def test_build_gold_balances_and_nonempty() -> None:
    """3 витрины + features непусты; SUM(listing_count) = COUNT(*) silver (крит.1, I-13)."""
    assert run_build_gold(None, _gcfg()) == EXIT_OK
    silver = _q("SELECT count(*) FROM iceberg.silver.apartments_clean")[0][0]
    assert silver > 0, "silver пуст — запусти make transform-demo"
    sum_by_district = _q(
        "SELECT sum(listing_count) FROM iceberg.gold.mart_price_area_by_district"
    )[0][0]
    assert sum_by_district == silver
    for t in ("mart_price_area_by_district", "mart_style_renovation_furniture",
              "mart_listing_dynamics", "apartments_features"):
        assert _q(f"SELECT count(*) FROM iceberg.gold.{t}")[0][0] > 0
    # is_loft всегда NULL (крит.3)
    assert _q(
        "SELECT count(*) FROM iceberg.gold.apartments_features WHERE is_loft IS NOT NULL"
    )[0][0] == 0
    # журнал: запись stage='build_gold' на каждую цель со snapshot_id (крит.5)
    marts_journaled = _q(
        "SELECT count(DISTINCT target_table) FROM iceberg.ops.pipeline_runs "
        "WHERE stage='build_gold' AND status='success'"
    )[0][0]
    assert marts_journaled >= 4


def test_features_schema_stable_across_rebuild() -> None:
    """DESCRIBE apartments_features одинаков до/после пересчёта (frozen, крит.3/US-4)."""
    run_build_gold("apartments_features", _gcfg())
    before = _q("DESCRIBE iceberg.gold.apartments_features")
    run_build_gold("apartments_features", _gcfg())
    after = _q("DESCRIBE iceberg.gold.apartments_features")
    assert before == after


def test_determinism_same_snapshot() -> None:
    """Повторный build на том же snapshot → то же содержимое (детерминизм, крит.2)."""
    run_build_gold("mart_price_area_by_district", _gcfg())
    first = _q(
        "SELECT district, listing_count, avg_price_rub, median_price_rub "
        "FROM iceberg.gold.mart_price_area_by_district ORDER BY district"
    )
    run_build_gold("mart_price_area_by_district", _gcfg())
    second = _q(
        "SELECT district, listing_count, avg_price_rub, median_price_rub "
        "FROM iceberg.gold.mart_price_area_by_district ORDER BY district"
    )
    assert first == second


def test_empty_silver_yields_empty_marts() -> None:
    """Пустой silver → пустые витрины без падения (FR-010, крит.4). Проверка на temp-пустой."""
    tmp = f"iceberg.gold.__empty_{uuid.uuid4().hex[:8]}"
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(f"CREATE TABLE {tmp} {_EMPTY_LIKE}")
        cur.fetchall()
        for builder in marts.MARTS.values():
            m = builder("a" * 32, 3, None)          # None snapshot -> SILVER без time-travel
            sql = m.select_sql.replace(marts.SILVER, tmp)
            cur.execute(sql, m.params)
            assert cur.fetchall() == []             # пустая витрина, не ошибка
        fm = features.features_sql("a" * 32, None)
        cur.execute(fm.select_sql.replace(marts.SILVER, tmp), fm.params)
        assert cur.fetchall() == []
    finally:
        c2 = conn.cursor()
        c2.execute(f"DROP TABLE IF EXISTS {tmp}")
        c2.fetchall()
        conn.close()


def test_defensive_nulls_area_zero() -> None:
    """price_per_m2 NULL при area=0; floor_ratio NULL при floors_total=0; is_loft NULL (крит.3)."""
    tmp = f"iceberg.gold.__edge_{uuid.uuid4().hex[:8]}"
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(f"CREATE TABLE {tmp} {_EMPTY_LIKE}")
        cur.fetchall()
        cur.execute(
            f"INSERT INTO {tmp} (id, source, external_id, price_rub, area_m2, floor, floors_total) "
            "VALUES ('x', 's', 'e', CAST(100 AS DECIMAL(12,2)), CAST(0 AS DECIMAL(8,2)), 3, 0)"
        )
        cur.fetchall()
        fm = features.features_sql("a" * 32, None)
        cur.execute(fm.select_sql.replace(marts.SILVER, tmp), fm.params)
        cols = [d[0] for d in cur.description]
        rec = dict(zip(cols, cur.fetchall()[0], strict=True))
        assert rec["price_per_m2"] is None     # NULLIF(area_m2, 0)
        assert rec["floor_ratio"] is None       # floors_total = 0
        assert rec["is_loft"] is None           # константа
    finally:
        d = conn.cursor()
        d.execute(f"DROP TABLE IF EXISTS {tmp}")
        d.fetchall()
        conn.close()


def test_swap_during_read_no_error() -> None:
    """Витрина читаема во время пересчёта: CREATE OR REPLACE атомарен, нет not-found (крит.2)."""
    run_build_gold("mart_price_area_by_district", _gcfg())  # гарантируем существование
    errors: list[str] = []

    def rebuild():
        try:
            run_build_gold("mart_price_area_by_district", _gcfg())
        except Exception as exc:  # noqa: BLE001
            errors.append(f"build: {exc}")

    t = threading.Thread(target=rebuild)
    t.start()
    reads = 0
    while t.is_alive() or reads < 20:
        try:
            n = _q("SELECT count(*) FROM iceberg.gold.mart_price_area_by_district")[0][0]
            assert n >= 0
            reads += 1
        except Exception as exc:  # noqa: BLE001 — любая ошибка чтения = провал (not-found окно)
            errors.append(f"read: {exc}")
        if reads >= 40:
            break
    t.join()
    assert not errors, f"чтение/пересборка дали ошибки: {errors[:3]}"
    assert reads >= 20
