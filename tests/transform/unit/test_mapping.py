"""Юнит-тесты mapping-конфигов (FR-002): загрузка, валидация, config_hash, цепочка примитивов."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from loftnav.transform.mapping import (
    MappingError,
    load_mapping,
    validate_against_bronze,
)

_CAP = 64 * 1024


def _write(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / f"{name}.toml"
    p.write_text(body, encoding="utf-8")
    return p


def test_load_and_apply_chain(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        "apartments",
        """
[meta]
external_id = "id"

[fields.price_rub]
input = "price"
regex_replace = { pattern = ",", replacement = "." }
cast = "decimal"
unit_convert = { from = "thousands_rub", to = "rub" }

[fields.has_renovation]
input = "renov"
enum_map = { "евро" = true, "требует ремонта" = false }
""",
    )
    m = load_mapping(p)
    assert m.source == "apartments"
    assert m.external_id_column == "id"
    assert len(m.config_hash) == 64
    # price "1 500,50" тыс.руб -> 1500.50 -> ×1000 = 1500500.00
    assert m.fields["price_rub"].apply("1500,50", _CAP) == Decimal("1500500.00")
    # enum casefold exact-match
    assert m.fields["has_renovation"].apply("Евро", _CAP) is True
    with pytest.raises(Exception):  # noqa: B017 — enum miss -> NormalizationError
        m.fields["has_renovation"].apply("нет данных", _CAP)


def test_config_hash_changes_with_content(tmp_path: Path) -> None:
    a = _write(tmp_path, "s1", '[fields.rooms]\ninput = "r"\ncast = "bigint"\n')
    b = _write(tmp_path, "s2", '[fields.rooms]\ninput = "r"\ncast = "bigint"\ndefault = 1\n')
    assert load_mapping(a).config_hash != load_mapping(b).config_hash


def test_unknown_silver_field(tmp_path: Path) -> None:
    p = _write(tmp_path, "bad", '[fields.not_a_field]\ninput = "x"\n')
    with pytest.raises(MappingError, match="неизвестное silver-поле"):
        load_mapping(p)


def test_unknown_field_key(tmp_path: Path) -> None:
    p = _write(tmp_path, "bad", '[fields.rooms]\ninput = "r"\nbogus = 1\n')
    with pytest.raises(MappingError, match="неизвестные ключи"):
        load_mapping(p)


def test_invalid_cast(tmp_path: Path) -> None:
    p = _write(tmp_path, "bad", '[fields.rooms]\ninput = "r"\ncast = "int128"\n')
    with pytest.raises(MappingError, match="cast"):
        load_mapping(p)


def test_validate_against_bronze(tmp_path: Path) -> None:
    body = '[meta]\nexternal_id = "id"\n[fields.rooms]\ninput = "r"\ncast = "bigint"\n'
    p = _write(tmp_path, "s", body)
    m = load_mapping(p)
    # несуществующая колонка -> ошибка
    with pytest.raises(MappingError, match="отсутствует в bronze"):
        validate_against_bronze(m, {"id", "other"})
    # покрыто -> warning по непокрытой колонке "extra"
    warns = validate_against_bronze(m, {"id", "r", "extra"})
    assert any("extra" in w for w in warns)
