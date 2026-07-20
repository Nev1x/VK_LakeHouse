"""Потоковая запись датасета (FR-003/FR-008, T4/T5): единый проход, parquet+jsonl+sha256 на чанк.

ParquetWriter.write_table по чанкам (НЕ df.to_parquet — тот пишет целиком); jsonl-строки в файл;
sha256 инкрементально. Пиковая память ≤ чанк (данные идут в файлы на диске, не в RAM).
Decimal→СТРОКА в jsonl (сохраняет DECIMAL-точность, не float); timestamp→ISO.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal

import pyarrow as pa
import pyarrow.parquet as pq

_DECIMAL_RE = re.compile(r"^decimal\((\d+),\s*(\d+)\)$", re.IGNORECASE)


def pa_type(trino_type: str) -> pa.DataType:
    """trino-тип → pyarrow-тип (явная схема — стабильность типов между чанками, в т.ч. all-NULL)."""
    t = trino_type.strip().lower()
    m = _DECIMAL_RE.match(t)
    if m:
        return pa.decimal128(int(m.group(1)), int(m.group(2)))
    if t == "varchar" or t.startswith("varchar("):
        return pa.string()
    if t == "bigint":
        return pa.int64()
    if t == "integer":
        return pa.int32()
    if t == "double":
        return pa.float64()
    if t == "boolean":
        return pa.bool_()
    if t.startswith("timestamp"):
        return pa.timestamp("us")
    if t == "date":
        return pa.date32()
    return pa.string()  # fallback: сериализуем как строку


def build_schema(describe: list[tuple[str, str]]) -> pa.Schema:
    return pa.schema([(name, pa_type(typ)) for name, typ in describe])


def _jsonl_value(v: object) -> object:
    if isinstance(v, Decimal):
        return str(v)                        # DECIMAL → строка (точность), не float
    if isinstance(v, (_dt.datetime, _dt.date)):
        return v.isoformat()
    return v


@dataclass
class WriteResult:
    row_count: int
    parquet_sha256: str
    parquet_size: int
    jsonl_sha256: str
    jsonl_size: int


class DatasetWriter:
    """Единый проход: write_chunk(chunk) → parquet.write_table + jsonl-строки + инкремент sha."""

    def __init__(self, schema: pa.Schema, columns: list[str], parquet_path: str, jsonl_path: str):
        self._schema = schema
        self._columns = columns
        self._parquet_path = parquet_path
        self._jsonl_path = jsonl_path
        self._pq = pq.ParquetWriter(parquet_path, schema)
        self._jsonl = open(jsonl_path, "wb")
        self._jsonl_sha = hashlib.sha256()
        self._jsonl_size = 0
        self._rows = 0

    def write_chunk(self, chunk: list[dict]) -> None:
        if not chunk:
            return
        table = pa.Table.from_pylist(chunk, schema=self._schema)
        self._pq.write_table(table)
        for row in chunk:
            line = json.dumps(
                {c: _jsonl_value(row.get(c)) for c in self._columns}, ensure_ascii=False
            ) + "\n"
            data = line.encode("utf-8")
            self._jsonl.write(data)
            self._jsonl_sha.update(data)
            self._jsonl_size += len(data)
        self._rows += len(chunk)

    def close(self) -> WriteResult:
        self._pq.close()
        self._jsonl.close()
        # parquet sha — потоковым чтением файла (bounded RAM), не повторным GET из S3
        psha = hashlib.sha256()
        psize = 0
        with open(self._parquet_path, "rb") as fh:
            for block in iter(lambda: fh.read(1024 * 1024), b""):
                psha.update(block)
                psize += len(block)
        return WriteResult(
            row_count=self._rows,
            parquet_sha256=psha.hexdigest(),
            parquet_size=psize,
            jsonl_sha256=self._jsonl_sha.hexdigest(),
            jsonl_size=self._jsonl_size,
        )
