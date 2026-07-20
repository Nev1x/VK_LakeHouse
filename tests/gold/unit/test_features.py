"""Юнит-тесты SQL apartments_features (FR-004): is_loft NULL, NULLIF, floor_ratio, нет *."""

from __future__ import annotations

from loftnav.gold import features

_RID = "b" * 32
_SNAP = 987654321


def test_features_sql_invariants() -> None:
    m = features.features_sql(_RID, _SNAP)
    low = m.select_sql.lower()
    assert "select *" not in low
    # is_loft — ВСЕГДА NULL-константа, никаких style-эвристик (лже-таргет запрещён)
    assert 'CAST(NULL AS BOOLEAN) AS "is_loft"' in m.select_sql
    assert "ilike" not in low and "%loft%" not in low   # нет эвристики style ILIKE '%loft%'
    # price_per_m2 через NULLIF(area_m2,0); floor_ratio через CASE floors_total 0/NULL
    assert "NULLIF(area_m2, 0)" in m.select_sql
    assert "floors_total IS NULL OR floors_total = 0" in m.select_sql
    assert f"FOR VERSION AS OF {_SNAP}" in m.select_sql
    assert m.params == [str(_SNAP), _RID]          # snapshot_id, затем run_id


def test_features_columns_frozen() -> None:
    m = features.features_sql(_RID, _SNAP)
    assert m.columns[:6] == ("id", "source", "external_id", "price_rub", "area_m2", "price_per_m2")
    assert "is_loft" in m.columns
    assert m.columns[-1] == "_computed_at"


def test_features_none_snapshot() -> None:
    m = features.features_sql(_RID, None)
    assert m.params[0] == "none"
    assert "FOR VERSION AS OF" not in m.select_sql
