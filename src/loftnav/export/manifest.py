"""Манифест ML-датасета (FR-007, frozen по I-6). Валидный JSON, поле-множество = v1 контракта.

created_at — python-сторона (datetime.now(UTC)), не Trino. sha256 файлов — из инкремента записи.
Честность: target_populated=false (is_loft не размечен), photo_handling=links (фото не скачаны).
"""

from __future__ import annotations

import datetime as _dt
import json

from loftnav.export.schema import FEATURES_TABLE
from loftnav.gold.marts import GOLD_COLUMNS_VERSION

MANIFEST_SCHEMA_VERSION = 1
LOFTNAV_EXPORT_VERSION = "0.6.0"
MANIFEST_NAME = "manifest.json"


def build_manifest(
    *,
    dataset_version: str,
    run_id: str,
    snapshot: int | None,
    row_count: int,
    describe: list[tuple[str, str]],
    is_loft_null_count: int,
    formats: list[str],
    files: list[dict],
) -> dict:
    schema = [
        {
            "name": name,
            "type": typ,
            # null_count фиксируем для is_loft (target-заготовка): всегда = row_count
            "null_count": is_loft_null_count if name == "is_loft" else None,
        }
        for name, typ in describe
    ]
    return {
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "dataset_version": dataset_version,
        "created_at": _dt.datetime.now(_dt.UTC).isoformat(),
        "run_id": run_id,
        "source_table": FEATURES_TABLE,
        "source_snapshot_id": None if snapshot is None else str(snapshot),
        "gold_columns_version": GOLD_COLUMNS_VERSION,
        "row_count": row_count,
        "formats": formats,
        "photo_handling": "links",           # фото — ссылки, НЕ скачаны (FR-009)
        "target_populated": False,           # is_loft не размечен (US-5, честность)
        "schema": schema,
        "files": files,                       # [{path, format, sha256, size_bytes}]
        "loftnav_export_version": LOFTNAV_EXPORT_VERSION,
        "notes": {
            # типовое расхождение форматов: деньги/площадь в jsonl — СТРОКИ (DECIMAL-точность)
            "jsonl_decimal_as_string": True,
            "jsonl_timestamp_iso8601": True,
            "parquet_decimal_native": True,
        },
    }


def serialize(manifest: dict) -> bytes:
    return (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
