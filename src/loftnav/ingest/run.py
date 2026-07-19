"""Оркестрация ingestion (FR-010/FR-012/FR-013): файл — логическая единица, батч-устойчивость (I-8).

Поток на файл: hash → журнальный статус (skip/replay) → raw PUT → read → infer → bronze → rejects →
ОДИН INSERT в журнал (try/finally). Исключение на файле → журнал failed + продолжение батча.
"""

from __future__ import annotations

import datetime as _dt
import itertools
import json
import os
import sys
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from loftnav import quarantine, runlog
from loftnav.config import IngestConfig
from loftnav.ingest import bronze_writer
from loftnav.ingest.hashing import sha256_file
from loftnav.ingest.inference import (
    coerce_value,
    infer_type,
    sanitize_columns,
    sanitize_identifier,
)
from loftnav.ingest.raw_store import store_raw
from loftnav.ingest.readers import SUPPORTED_SUFFIXES, get_reader
from loftnav.io.s3 import S3Store
from loftnav.trino_client import get_connection

STAGE = "ingest"

# Exit codes (FR-012).
EXIT_OK = 0
EXIT_ALL_FAILED = 1
EXIT_PARTIAL = 2


@dataclass
class FileResult:
    path: Path
    status: str
    rows_ok: int = 0
    rows_quarantined: int = 0
    tables: list[str] = field(default_factory=list)
    error: str | None = None


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.UTC).replace(tzinfo=None)


def _log(run_id: str, step: str, **kw: object) -> None:
    """Structured key=value лог с run_id (FR-013/I-9)."""
    parts = " ".join(f"{k}={v}" for k, v in kw.items())
    print(f"run_id={run_id} step={step} {parts}", file=sys.stderr)


# --- lock процесса ingest (FR-011, I-15) ---


@contextmanager
def process_lock(cfg: IngestConfig) -> Iterator[None]:
    path = cfg.lock_path
    fd = None
    try:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            if _stale_lock(path):
                path.unlink(missing_ok=True)
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            else:
                raise RuntimeError(
                    f"ingest уже идёт (lock {path}); дождитесь завершения или снимите lock"
                ) from None
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        fd = None
        yield
    finally:
        if fd is not None:
            os.close(fd)
        path.unlink(missing_ok=True)


def _stale_lock(path: Path) -> bool:
    try:
        pid = int(path.read_text().strip() or "0")
    except (ValueError, OSError):
        return True
    if pid <= 0:
        return True
    try:
        os.kill(pid, 0)  # процесс жив?
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    return False


# --- namespace/таблицы ---


def _ensure_schemas(conn) -> None:
    cur = conn.cursor()
    for ns in ("bronze", "quarantine", "ops"):
        cur.execute(f"CREATE SCHEMA IF NOT EXISTS iceberg.{ns}")
        cur.fetchall()
    runlog.ensure_table(conn)


# --- обработка одного источника (лист/файл) ---


def _process_source(conn, source, records, ctx, cfg, replay) -> tuple[int, int, str | None, dict]:
    run_id, content_hash, source_file = ctx
    buffer = list(itertools.islice(records, cfg.read_chunk_rows))
    if not buffer:
        return 0, 0, None, {}

    raw_cols: list[str] = []
    seen: set[str] = set()
    for rec in buffer:
        for k in rec:
            if k not in seen:
                seen.add(k)
                raw_cols.append(k)
    sanitized = sanitize_columns(raw_cols)
    data_schema = {
        san: infer_type([rec.get(raw) for rec in buffer])
        for raw, san in zip(raw_cols, sanitized, strict=True)
    }

    effective = bronze_writer.ensure_table(conn, source, data_schema)
    if replay:
        bronze_writer.delete_by_content_hash(conn, source, content_hash)

    columns = [*sanitized, *(c for c, _ in bronze_writer.SERVICE_COLUMNS)]
    ingested_at = _now()
    valid_rows: list[list] = []
    rejects: list[quarantine.Reject] = []

    for rec in itertools.chain(buffer, records):
        try:
            row: list = []
            for raw, san in zip(raw_cols, sanitized, strict=True):
                v = rec.get(raw)
                if v is not None and len(v.encode("utf-8")) > cfg.max_field_bytes:
                    raise ValueError(f"поле {san} превышает лимит {cfg.max_field_bytes} байт")
                row.append(coerce_value(v, effective[san]))
            row.extend([run_id, content_hash, source_file, ingested_at])
            valid_rows.append(row)
        except Exception as exc:  # noqa: BLE001 — невалидная строка не роняет файл (I-8), едет в quarantine
            raw_json = json.dumps(rec, ensure_ascii=False)[: cfg.max_field_bytes]
            rejects.append(quarantine.Reject(raw_record=raw_json, reason=str(exc)))

    ok = bronze_writer.insert_rows(
        conn, source, columns, valid_rows,
        chunk_rows=cfg.insert_chunk_rows, chunk_bytes=cfg.insert_chunk_bytes,
    )
    q = quarantine.write_rejects(conn, run_id, source, "bronze", rejects)
    _log(run_id, "bronze", source=source, rows_ok=ok, rows_quarantined=q)
    return ok, q, bronze_writer.bronze_table(source), data_schema


# --- обработка одного файла ---


def process_file(
    conn, store, path: Path, source_override: str | None, cfg: IngestConfig
) -> FileResult:
    run_id = uuid.uuid4().hex
    started = _now()
    source_file = str(path)
    content_hash = ""
    status = runlog.STATUS_FAILED
    error: str | None = None
    rows_ok = rows_q = 0
    tables: list[str] = []
    schema_map: dict[str, dict] = {}

    try:
        size = path.stat().st_size
        if size == 0:
            raise ValueError("пустой файл (0 байт)")
        if size > cfg.max_file_bytes:
            raise ValueError(f"файл превышает лимит {cfg.max_file_bytes} байт")

        content_hash = sha256_file(path)
        prev = runlog.last_status(conn, content_hash)
        # success ИЛИ skipped => файл уже успешно загружен ранее => снова skip (не задваиваем).
        if prev in (runlog.STATUS_SUCCESS, runlog.STATUS_SKIPPED):
            status = runlog.STATUS_SKIPPED
            _log(run_id, "skip", file=path.name, reason=f"hash-match-{prev}")
            return FileResult(path, status)
        # failed/partial => replay: DELETE строк этого прогона + повторная вставка (FR-010).
        replay = prev in (runlog.STATUS_FAILED, runlog.STATUS_PARTIAL)

        key, stored = store_raw(store, path, content_hash)
        _log(run_id, "raw", key=key, stored=stored)

        reader = get_reader(path, cfg)
        default = sanitize_identifier(path.stem) or "source"
        base = sanitize_identifier(source_override) if source_override else default
        base = base or "source"

        for src in reader.sources(path):
            suffix = sanitize_identifier(f"{base}_{src.suffix}") if src.suffix else ""
            source = suffix or base
            ok, q, table, sch = _process_source(
                conn, source, src.records, (run_id, content_hash, source_file), cfg, replay
            )
            rows_ok += ok
            rows_q += q
            if table:
                tables.append(table)
                schema_map[table] = sch

        status = runlog.STATUS_PARTIAL if rows_q > 0 else runlog.STATUS_SUCCESS
    except bronze_writer.SchemaConflict as exc:
        status = runlog.STATUS_FAILED
        error = f"schema conflict: {exc}"
    except Exception as exc:  # noqa: BLE001 — сбой файла не роняет батч (I-8/FR-012)
        status = runlog.STATUS_FAILED
        error = str(exc)
    finally:
        # журнальная запись пишется ВСЕГДА (в т.ч. skipped/failed) — NFR-003, один INSERT (I-3)
        finished = _now()
        rec = runlog.RunRecord(
            run_id=run_id,
            stage=STAGE,
            started_at=started,
            finished_at=finished,
            source_file=source_file,
            content_hash=content_hash,
            target_table=";".join(tables) or None,
            rows_ok=rows_ok,
            rows_quarantined=rows_q,
            schema_json=json.dumps(schema_map, ensure_ascii=False) if schema_map else None,
            status=status,
            error_message=error,
        )
        try:
            runlog.record_run(conn, rec)
        except Exception as jexc:  # noqa: BLE001 — журнал не должен рушить процесс
            _log(run_id, "journal_error", error=str(jexc))

    return FileResult(path, status, rows_ok, rows_q, tables, error)


# --- батч ---


def _collect_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for p in paths:
        if p.is_dir():
            for child in sorted(p.iterdir()):
                if child.is_file() and child.suffix.lower() in SUPPORTED_SUFFIXES:
                    files.append(child)
        elif p.is_file():
            files.append(p)
        else:
            raise FileNotFoundError(f"путь не найден: {p}")
    return files


def ingest_paths(paths: list[Path], source_override: str | None, cfg: IngestConfig) -> int:
    files = _collect_files(paths)
    if not files:
        print("ingest: нет поддерживаемых файлов для загрузки")
        return EXIT_OK

    with process_lock(cfg):
        store = S3Store(cfg)
        conn = get_connection()
        try:
            _ensure_schemas(conn)
            results = [process_file(conn, store, f, source_override, cfg) for f in files]
        finally:
            conn.close()

    _print_summary(results)
    failed = [r for r in results if r.status == runlog.STATUS_FAILED]
    if not failed:
        return EXIT_OK
    if len(failed) == len(results):
        return EXIT_ALL_FAILED
    return EXIT_PARTIAL


def _print_summary(results: list[FileResult]) -> None:
    print("\n=== ingest summary ===")
    for r in results:
        line = f"  [{r.status:8}] {r.path.name}  ok={r.rows_ok} quarantined={r.rows_quarantined}"
        if r.error:
            line += f"  error={r.error}"
        print(line)
