"""Оркестрация export-dataset (FR-001/FR-006/FR-010..FR-012): единый проход, immutable vNNN.

Порядок записи: data-файлы ПЕРВЫМИ, manifest.json ПОСЛЕДНИМ (маркер валидности версии) — частичный
сбой оставляет версию без манифеста = невалидна. Общий pipeline-lock; журнал stage='export'.
Фото — passthrough (0 исходящих HTTP). Значения — bind/явные, идентификаторы — явные frozen-колонки.
"""

from __future__ import annotations

import datetime as _dt
import json
import shutil
import sys
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from loftnav import runlog
from loftnav.config import ExportConfig
from loftnav.export import manifest as manifest_mod
from loftnav.export import schema, versioning, writer
from loftnav.ingest.run import process_lock
from loftnav.io.s3 import S3Store
from loftnav.trino_client import get_connection

STAGE = "export"
EXIT_OK = 0
EXIT_FAILED = 1

_FORMATS = {"parquet": "data.parquet", "jsonl": "data.jsonl"}


@dataclass
class ExportResult:
    version: str | None
    status: str
    row_count: int = 0
    files: list[str] = field(default_factory=list)
    error: str | None = None


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.UTC).replace(tzinfo=None)


def _log(run_id: str, step: str, **kw: object) -> None:
    parts = " ".join(f"{k}={v}" for k, v in kw.items())
    print(f"run_id={run_id} stage=export step={step} {parts}", file=sys.stderr)


def _selected_formats(fmt: str) -> list[str]:
    if fmt == "both":
        return ["parquet", "jsonl"]
    if fmt in _FORMATS:
        return [fmt]
    raise ValueError(f"неизвестный --format {fmt!r} (parquet|jsonl|both)")


def run_export(fmt: str, ecfg: ExportConfig) -> int:
    formats = _selected_formats(fmt)
    run_id = uuid.uuid4().hex
    started = _now()
    status = runlog.STATUS_FAILED
    err: str | None = None
    version: str | None = None
    rows = 0
    snapshot: int | None = None
    files_out: list[str] = []
    tmpdir = Path(tempfile.mkdtemp(prefix="loftnav-export-"))

    with process_lock(ecfg):
        conn = get_connection()
        store = S3Store(ecfg, ecfg.datasets_bucket)
        try:
            snapshot = schema.snapshot_id(conn)
            describe = schema.describe(conn)
            null_ct = schema.is_loft_null_count(conn, snapshot)
            version = versioning.next_version(store)
            prefix = f"{versioning.DATASETS_PREFIX}{version}/"
            _log(run_id, "start", version=version, snapshot=snapshot)

            # --- единый read-loop: fetchmany → parquet.write_table + jsonl + sha (один проход) ---
            parquet_path = str(tmpdir / "data.parquet")
            jsonl_path = str(tmpdir / "data.jsonl")
            w = writer.DatasetWriter(
                writer.build_schema(describe), list(schema.FEATURES_COLUMNS),
                parquet_path, jsonl_path,
            )
            cur = conn.cursor()
            cur.execute(schema.select_sql(snapshot))
            colnames = [d[0] for d in cur.description]
            while True:
                batch = cur.fetchmany(ecfg.read_chunk_rows)
                if not batch:
                    break
                w.write_chunk([dict(zip(colnames, r, strict=True)) for r in batch])
            result = w.close()
            rows = result.row_count
            if rows == 0:
                _log(run_id, "warn", msg="features пуст — валидная ПУСТАЯ версия (row_count=0)")

            # --- запись: data-файлы ПЕРВЫМИ (fail-loud коллизия), манифест ПОСЛЕДНИМ ---
            paths = {"parquet": parquet_path, "jsonl": jsonl_path}
            shas = {"parquet": (result.parquet_sha256, result.parquet_size),
                    "jsonl": (result.jsonl_sha256, result.jsonl_size)}
            files_meta: list[dict] = []
            for f in formats:
                key = f"{prefix}{_FORMATS[f]}"
                store.upload_or_fail(key, paths[f])
                sha, size = shas[f]
                files_meta.append(
                    {"path": _FORMATS[f], "format": f, "sha256": sha, "size_bytes": size}
                )
                files_out.append(_FORMATS[f])

            m = manifest_mod.build_manifest(
                dataset_version=version, run_id=run_id, snapshot=snapshot, row_count=rows,
                describe=describe, is_loft_null_count=null_ct, formats=formats, files=files_meta,
            )
            store.put_or_fail(f"{prefix}{manifest_mod.MANIFEST_NAME}", manifest_mod.serialize(m))
            files_out.append(manifest_mod.MANIFEST_NAME)
            status = runlog.STATUS_SUCCESS
            _log(run_id, "done", version=version, rows_ok=rows, files=files_out)
        except Exception as exc:  # noqa: BLE001 — читаемая ошибка + журнал failed (I-8)
            err = str(exc)
            _log(run_id, "failed", version=version, error=err)
        finally:
            _record(conn, run_id, version, snapshot, rows, status, err, started)
            conn.close()
            shutil.rmtree(tmpdir, ignore_errors=True)

    _print_summary(ExportResult(version, status, rows, files_out, err))
    return EXIT_OK if status == runlog.STATUS_SUCCESS else EXIT_FAILED


def _record(conn, run_id, version, snapshot, rows, status, err, started) -> None:
    rec = runlog.RunRecord(
        run_id=run_id, stage=STAGE, started_at=started, finished_at=_now(),
        source_file=version or "(no-version)",
        content_hash="none" if snapshot is None else str(snapshot),
        target_table=f"{versioning.DATASETS_PREFIX}{version}" if version else "(none)",
        rows_ok=rows, rows_quarantined=0,
        schema_json=json.dumps({"manifest_schema_version": manifest_mod.MANIFEST_SCHEMA_VERSION}),
        status=status, error_message=err,
    )
    try:
        runlog.record_run(conn, rec)
    except Exception as jexc:  # noqa: BLE001 — журнал не рушит процесс
        _log(run_id, "journal_error", error=str(jexc))


def _print_summary(r: ExportResult) -> None:
    print("\n=== export-dataset summary ===")
    line = f"  [{r.status:8}] {r.version or '-'}  rows_ok={r.row_count}  files={r.files}"
    if r.error:
        line += f"  error={r.error}"
    print(line)
