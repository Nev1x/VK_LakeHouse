"""Юнит-тесты ридеров на фикстурах (без стека): CSV cp1251/;, XLSX листы+merged, JSONL, binary."""

from __future__ import annotations

import pytest

from loftnav.ingest.readers import get_reader
from loftnav.ingest.readers.csv_reader import CsvReader
from loftnav.ingest.readers.excel_reader import ExcelReader
from loftnav.ingest.readers.json_reader import JsonReader


def test_csv_cp1251_semicolon_comma_decimal(fixtures_dir, make_config) -> None:
    reader = CsvReader(make_config())
    sources = list(reader.sources(fixtures_dir / "apartments.csv"))
    assert len(sources) == 1
    records = list(sources[0].records)
    assert len(records) == 5
    first = records[0]
    assert first["city"] == "Москва"          # cp1251 кириллица цела
    assert first["area"] == "45,5"             # запятая-десятичная сохранена как есть
    assert "_note" in first                     # сырое имя (санитизация -> u_note позже)


def test_excel_two_sheets_and_merged(fixtures_dir, make_config) -> None:
    reader = ExcelReader(make_config())
    sources = list(reader.sources(fixtures_dir / "listings.xlsx"))
    suffixes = {s.suffix for s in sources}
    assert suffixes == {"flats", "meta"}
    flats = next(s for s in sources if s.suffix == "flats")
    rows = list(flats.records)
    assert len(rows) == 4
    # merged cell: не-anchor ячейка -> None (значение в левой-верхней)
    merged_row = rows[-1]
    assert None in merged_row.values()


def test_jsonl_nested_object_serialized(fixtures_dir, make_config) -> None:
    reader = JsonReader(make_config())
    sources = list(reader.sources(fixtures_dir / "flats.jsonl"))
    records = list(sources[0].records)
    assert len(records) == 3
    assert records[0]["location"].startswith("{")     # вложенный объект -> JSON-строка
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
