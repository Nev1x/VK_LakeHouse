"""Юнит-тесты writer/manifest (FR-003/FR-007/FR-008): encoder, pa-типы, потоковая запись."""

from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal

import pandas as pd
import pyarrow as pa

from loftnav.export import manifest as manifest_mod
from loftnav.export import writer


def test_jsonl_value_decimal_as_string() -> None:
    assert writer._jsonl_value(Decimal("1234.56")) == "1234.56"       # DECIMAL -> строка, не float
    assert writer._jsonl_value(dt.datetime(2026, 1, 2, 10, 0)) == "2026-01-02T10:00:00"
    assert writer._jsonl_value(dt.date(2026, 1, 2)) == "2026-01-02"
    assert writer._jsonl_value(None) is None
    assert writer._jsonl_value(5) == 5


def test_pa_type_mapping() -> None:
    assert writer.pa_type("decimal(12,2)") == pa.decimal128(12, 2)
    assert writer.pa_type("bigint") == pa.int64()
    assert writer.pa_type("double") == pa.float64()
    assert writer.pa_type("boolean") == pa.bool_()
    assert writer.pa_type("varchar") == pa.string()
    assert writer.pa_type("timestamp(6)") == pa.timestamp("us")


def test_streaming_write_roundtrip(tmp_path) -> None:
    describe = [("id", "varchar"), ("price_rub", "decimal(12,2)"), ("rooms", "bigint")]
    cols = [n for n, _ in describe]
    pqp, jlp = str(tmp_path / "d.parquet"), str(tmp_path / "d.jsonl")
    w = writer.DatasetWriter(writer.build_schema(describe), cols, pqp, jlp)
    w.write_chunk([{"id": "a", "price_rub": Decimal("100.00"), "rooms": 2}])
    w.write_chunk([{"id": "b", "price_rub": Decimal("200.50"), "rooms": None}])
    res = w.close()
    assert res.row_count == 2
    # parquet читается pandas НЕЗАВИСИМО; decimal нативен
    df = pd.read_parquet(pqp)
    assert list(df["id"]) == ["a", "b"] and df["price_rub"][0] == Decimal("100.00")
    # jsonl: decimal — строка
    lines = [json.loads(x) for x in open(jlp, encoding="utf-8").read().splitlines()]
    assert lines[0]["price_rub"] == "100.00" and lines[1]["rooms"] is None
    assert len(res.parquet_sha256) == 64 and len(res.jsonl_sha256) == 64


def test_manifest_structure_and_json(tmp_path) -> None:
    m = manifest_mod.build_manifest(
        dataset_version="v001", run_id="r" * 32, snapshot=12345, row_count=3,
        describe=[("id", "varchar"), ("is_loft", "boolean")], is_loft_null_count=3,
        formats=["parquet", "jsonl"],
        files=[{"path": "data.parquet", "format": "parquet", "sha256": "x", "size_bytes": 1}],
    )
    assert m["manifest_schema_version"] == 1
    assert m["target_populated"] is False           # is_loft не размечен (честность)
    assert m["photo_handling"] == "links"           # фото — ссылки
    assert m["source_snapshot_id"] == "12345"
    assert m["notes"]["jsonl_decimal_as_string"] is True
    isloft = next(s for s in m["schema"] if s["name"] == "is_loft")
    assert isloft["null_count"] == 3
    dt.datetime.fromisoformat(m["created_at"])       # валидный ISO
    json.loads(manifest_mod.serialize(m).decode())   # валидный JSON
