"""Юнит-тесты ридеров на фикстурах (без стека): CSV cp1251/;, XLSX листы+merged, JSONL, binary."""

from __future__ import annotations

import pytest

from loftnav.ingest.inference import sanitize_columns
from loftnav.ingest.readers import get_reader
from loftnav.ingest.readers.csv_reader import CsvReader
from loftnav.ingest.readers.excel_reader import ExcelReader
from loftnav.ingest.readers.json_reader import JsonReader


def test_csv_cp1251_semicolon_comma_decimal(fixtures_dir, make_config) -> None:
    reader = CsvReader(make_config())
    sources = list(reader.sources(fixtures_dir / "apartments.csv"))
    assert len(sources) == 1
    src = sources[0]
    assert src.header == ["id", "city", "area", "price", "_note"]  # сырой заголовок, без мэнглинга
    records = list(src.records)
    assert len(records) == 5
    assert records[0][1] == "Москва"    # позиционно: city (индекс 1), cp1251 цела
    assert records[0][2] == "45,5"      # запятая-десятичная сохранена


def test_csv_empty_and_duplicate_header(tmp_path, make_config) -> None:
    """Пустой/дублирующийся заголовок -> сырьё цело; sanitize_columns => col_N/_2 (WARNING-1)."""
    p = tmp_path / "dup.csv"
    p.write_text("a,,a,b\n1,2,3,4\n", encoding="utf-8")
    src = next(iter(CsvReader(make_config()).sources(p)))
    assert src.header == ["a", "", "a", "b"]                 # НЕ pandas 'Unnamed: 1' / 'a.1'
    assert sanitize_columns(src.header) == ["a", "col_1", "a_2", "b"]


def test_excel_two_sheets_and_merged(fixtures_dir, make_config) -> None:
    reader = ExcelReader(make_config())
    sources = list(reader.sources(fixtures_dir / "listings.xlsx"))
    assert {s.suffix for s in sources} == {"flats", "meta"}
    flats = next(s for s in sources if s.suffix == "flats")
    assert flats.header == ["id", "rooms", "price"]
    rows = list(flats.records)
    assert len(rows) == 4
    assert None in rows[-1]  # merged cell: не-anchor ячейка -> None


def test_jsonl_nested_object_serialized(fixtures_dir, make_config) -> None:
    reader = JsonReader(make_config())
    sources = list(reader.sources(fixtures_dir / "flats.jsonl"))
    assert sources[0].header is None
    records = list(sources[0].records)
    assert len(records) == 3
    assert records[0]["location"].startswith("{")   # вложенный объект -> JSON-строка
    assert records[0]["balcony"] == "true"


def test_broken_binary_detected(fixtures_dir, make_config) -> None:
    reader = get_reader(fixtures_dir / "broken.csv", make_config())
    with pytest.raises(ValueError, match="бинарн"):
        list(reader.sources(fixtures_dir / "broken.csv"))


def test_unsupported_format_rejected(tmp_path, make_config) -> None:
    p = tmp_path / "data.parquet"
    p.write_bytes(b"x")
    with pytest.raises(ValueError, match="неподдерживаемый"):
        get_reader(p, make_config())
