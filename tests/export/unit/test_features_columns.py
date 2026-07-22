"""Frozen-контракт числа/порядка колонок экспорта (FR-004/FR-005, 007). Чистая логика без стека.

Точное число колонок = 26 (23 базовых 006 + 3 лофт-маркера 007). Список export/schema.py обязан
byte-в-byte совпадать с порядком колонок gold/features.py — иначе parquet-схема и SELECT разъедутся.
"""

from __future__ import annotations

from loftnav.export.schema import FEATURES_COLUMNS
from loftnav.gold import features

_MARKERS = ("ceiling_height_m", "wall_material", "year_built")
_EXPORT_COLUMN_COUNT = 26


def test_export_column_count_is_26() -> None:
    assert len(FEATURES_COLUMNS) == _EXPORT_COLUMN_COUNT
    # без дублей
    assert len(set(FEATURES_COLUMNS)) == _EXPORT_COLUMN_COUNT


def test_export_columns_match_features_order() -> None:
    m = features.features_sql("b" * 32, 1)
    assert tuple(m.columns) == FEATURES_COLUMNS       # порядок идентичен features_sql
    assert len(m.columns) == _EXPORT_COLUMN_COUNT


def test_markers_present_and_before_is_loft() -> None:
    for col in _MARKERS:
        assert col in FEATURES_COLUMNS
    idx_is_loft = FEATURES_COLUMNS.index("is_loft")
    # три маркера — ровно перед is_loft (позиции важны: frozen-тест features проверяет их)
    assert FEATURES_COLUMNS[idx_is_loft - 3:idx_is_loft] == _MARKERS
    # сервисный хвост не сдвинут
    assert FEATURES_COLUMNS[-1] == "_computed_at"
