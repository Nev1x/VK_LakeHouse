"""Юнит-тесты санитизации идентификаторов (инъекции) и schema inference (FR-003/FR-004, I-7)."""

from __future__ import annotations

import re

import pytest

from loftnav.ingest.inference import (
    coerce_value,
    infer_type,
    quote_ident,
    sanitize_columns,
    sanitize_identifier,
)

_SAFE = re.compile(r"^[a-z0-9_]+$")


@pytest.mark.parametrize(
    "raw",
    [
        'x"; DROP TABLE users--',
        "'; DELETE FROM bronze; --",
        "a` OR 1=1 --",
        "col name with spaces",
        "ПлохоеИмя",
    ],
)
def test_sanitize_no_sql_injection(raw: str) -> None:
    s = sanitize_identifier(raw)
    # результат либо пуст (=> col_N у caller), либо строго в whitelist без кавычек/точек-с-запятой
    assert s == "" or _SAFE.match(s), f"небезопасный идентификатор: {s!r}"
    assert '"' not in s and ";" not in s and "'" not in s and "-" not in s


def test_sanitize_rules() -> None:
    assert sanitize_identifier("Price ") == "price"
    assert sanitize_identifier("123col") == "c_123col"     # не начинается с цифры
    assert sanitize_identifier("_note") == "u_note"        # пользовательский _-префикс -> u_
    assert sanitize_identifier("цена") == ""               # не-ASCII -> пусто (caller даст col_N)
    assert sanitize_identifier("") == ""


def test_sanitize_columns_dedup_and_empty() -> None:
    assert sanitize_columns(["a", "a", "a"]) == ["a", "a_2", "a_3"]
    assert sanitize_columns(["", "цена"]) == ["col_0", "col_1"]
    assert sanitize_columns(["_x", "_x"]) == ["u_x", "u_x_2"]


def test_quote_ident_rejects_unsanitized() -> None:
    assert quote_ident("price") == '"price"'
    with pytest.raises(ValueError):
        quote_ident('bad"; drop')


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        (["1", "2", "3"], "BIGINT"),
        (["1.5", "2.0", "-3.25"], "DOUBLE"),
        (["1234,56"], "VARCHAR"),          # запятая-десятичная остаётся VARCHAR
        (["true", "false"], "BOOLEAN"),
        (["2020-01-01", "2021-12-31"], "DATE"),
        (["2020-01-01T10:00:00"], "TIMESTAMP"),
        (["a", "1"], "VARCHAR"),           # конфликт -> VARCHAR
        ([], "VARCHAR"),
        ([None, ""], "VARCHAR"),
    ],
)
def test_infer_type(values, expected) -> None:
    assert infer_type(values) == expected


def test_coerce_value() -> None:
    assert coerce_value("5", "BIGINT") == 5
    assert coerce_value("1.5", "DOUBLE") == 1.5
    assert coerce_value("true", "BOOLEAN") is True
    assert coerce_value(None, "BIGINT") is None
    assert coerce_value("", "BIGINT") is None
    with pytest.raises(ValueError):
        coerce_value("n/a", "BIGINT")     # невалидное значение -> строка в quarantine
