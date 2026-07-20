"""Юнит-тесты примитивов нормализации (FR-004): Decimal-цепочка, unit_convert, sanity, ReDoS-cap."""

from __future__ import annotations

import datetime as dt
import time
from decimal import Decimal

import pytest

from loftnav.config import SANITY_DEFAULTS
from loftnav.transform import normalize


def test_cast_decimal_exact_no_float() -> None:
    assert normalize.cast_decimal("1234.56") == Decimal("1234.56")
    assert normalize.cast_decimal("0.1") == Decimal("0.10")   # quantize до копеек
    with pytest.raises(normalize.NormalizationError):
        normalize.cast_decimal("abc")


def test_regex_replace_comma_decimal() -> None:
    v = normalize.regex_replace("1234,56", ",", ".", 64 * 1024)
    assert normalize.cast_decimal(v) == Decimal("1234.56")


@pytest.mark.parametrize(
    ("frm", "to", "value", "expected"),
    [
        ("thousands_rub", "rub", "1500", "1500000.00"),
        ("mln_rub", "rub", "3.5", "3500000.00"),
        ("sotka", "m2", "6", "600.00"),
        ("rub", "rub", "100", "100.00"),
    ],
)
def test_unit_convert(frm, to, value, expected) -> None:
    got = normalize.unit_convert(normalize.cast_decimal(value), frm, to)
    assert got == Decimal(expected)


def test_unit_convert_unknown_raises() -> None:
    with pytest.raises(normalize.NormalizationError):
        normalize.unit_convert(Decimal("1"), "furlong", "m2")


def test_casts() -> None:
    assert normalize.cast_bigint("3") == 3
    assert normalize.cast_boolean("да") is True
    assert normalize.cast_boolean("нет") is False
    assert normalize.cast_timestamp("2026-01-02T10:00:00") == dt.datetime(2026, 1, 2, 10, 0, 0)
    with pytest.raises(normalize.NormalizationError):
        normalize.cast_bigint("3.5")


def test_regex_value_cap_blocks_long_value() -> None:
    """ReDoS defense: значение длиннее cap → ошибка ДО запуска regex (bounded время)."""
    pathological = "(a+)+$"
    payload = "a" * 100_000  # > cap
    start = time.monotonic()
    with pytest.raises(normalize.NormalizationError, match="ReDoS"):
        normalize.regex_replace(payload, pathological, "x", cap=64 * 1024)
    assert time.monotonic() - start < 1.0  # не зависли на катастрофическом backtracking


@pytest.mark.parametrize(
    ("field", "value", "ok"),
    [
        ("price_rub", Decimal("0"), False),      # > 0 эксклюзивно
        ("price_rub", Decimal("100.00"), True),
        ("area_m2", Decimal("0.5"), False),
        ("area_m2", Decimal("50.00"), True),
        ("area_m2", Decimal("2000"), False),
        ("rooms", 25, False),
        ("rooms", 3, True),
    ],
)
def test_sanity_ok(field, value, ok) -> None:
    assert normalize.sanity_ok(field, value, SANITY_DEFAULTS) is ok
