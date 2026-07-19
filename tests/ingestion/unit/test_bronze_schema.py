"""Юнит-тесты промоций типов bronze (FR-007) — чистая логика без стека."""

from __future__ import annotations

import pytest

from loftnav.ingest.bronze_writer import SchemaConflict, resolve_column_type


def test_equal_types() -> None:
    assert resolve_column_type("BIGINT", "BIGINT") == "BIGINT"


@pytest.mark.parametrize(
    ("existing", "new"),
    [("BIGINT", "DOUBLE"), ("INTEGER", "BIGINT"), ("REAL", "DOUBLE"), ("DOUBLE", "BIGINT")],
)
def test_allowed_promotions_keep_existing(existing: str, new: str) -> None:
    # существующая колонка авторитетна (additive, I-6)
    assert resolve_column_type(existing, new) == existing


@pytest.mark.parametrize(
    ("existing", "new"),
    [("VARCHAR", "BIGINT"), ("BIGINT", "VARCHAR"), ("DATE", "BIGINT"), ("BOOLEAN", "DOUBLE")],
)
def test_incompatible_raises(existing: str, new: str) -> None:
    with pytest.raises(SchemaConflict):
        resolve_column_type(existing, new)
