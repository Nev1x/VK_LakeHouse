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


@dataclass
class _Counters:
    """Живые счётчики ФАКТИЧЕСКИ закоммиченного (обновляются только после успешной вставки).

    Журнал (в т.ч. при сбое посреди файла) отражает эти значения — CRITICAL-1/NFR-003/I-2.
    """
    rows_ok: int = 0
    rows_quarantined: int = 0


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


def _rows_and_header(src, chunk_rows: int) -> tuple[list[str | None], list[list], object]:
    """Приводит источник к позиционной модели: (сырые имена, буфер-строк, поток остатка).

    Табличные форматы (header != None) уже позиционные; JSON (dict-записи) — union ключей буфера.
    """
    if src.header is not None:
        buffer = list(itertools.islice(src.records, chunk_rows))
        return list(src.header), buffer, src.records
    buf_dicts = list(itertools.islice(src.records, chunk_rows))
    raw_cols: list[str] = []
    seen: set[str] = set()
    for d in buf_dicts:
        for k in d:
            if k not in seen:
                seen.add(k)
                raw_cols.append(k)
    buffer = [[d.get(c) for c in raw_cols] for d in buf_dicts]
    rest = ([d.get(c) for c in raw_cols] for d in src.records)
    return raw_cols, buffer, rest


def _make_reject(raw_cols: list[str | None], row: list, reason: str, cfg) -> quarantine.Reject:
    """Строит reject с ВАЛИДНЫМ JSON; при превышении — {_truncated, _original_bytes, _prefix}."""
    obj = {
        (name if isinstance(name, str) and name else f"col_{i}"): (row[i] if i < len(row) else None)
        for i, name in enumerate(raw_cols)
    }
    raw = json.dumps(obj, ensure_ascii=False, default=str)
    data = raw.encode("utf-8")
    if len(data) > cfg.max_field_bytes:
        prefix = data[: max(0, cfg.max_field_bytes - 128)].decode("utf-8", errors="ignore")
        raw = json.dumps(
            {"_truncated": True, "_original_bytes": len(data), "_prefix": prefix},
            ensure_ascii=False,
        )
    return quarantine.Reject(raw_record=raw, reason=reason)


def _process_source(conn, source, src, ctx, cfg, replay, counters) -> tuple[str | None, dict]:
    """Стрим источника: инкрементальный коммит bronze/rejects; счётчики = ФАКТ (CRITICAL-1)."""
    run_id, content_hash, source_file = ctx
    raw_cols, buffer, rest = _rows_and_header(src, cfg.read_chunk_rows)
    if not buffer:
        return None, {}

    sanitized = sanitize_columns(raw_cols)
    data_schema = {
        san: infer_type([row[i] if i < len(row) else None for row in buffer])
        for i, san in enumerate(sanitized)
    }
    effective = bronze_writer.ensure_table(conn, source, data_schema)
    if replay:
        bronze_writer.delete_by_content_hash(conn, source, content_hash)

    columns = [*sanitized, *(c for c, _ in bronze_writer.SERVICE_COLUMNS)]
    prefix_len = bronze_writer.insert_prefix_len(source, columns)
    service = [run_id, content_hash, source_file, _now()]
    valid_batch: list[list] = []
    valid_sql = prefix_len
    reject_batch: list[quarantine.Reject] = []

    def flush_valid() -> None:
        nonlocal valid_batch, valid_sql
        if valid_batch:
            bronze_writer.insert_batch(conn, source, columns, valid_batch)
            counters.rows_ok += len(valid_batch)  # обновляем ТОЛЬКО после коммита
            valid_batch, valid_sql = [], prefix_len

    def flush_rejects() -> None:
        nonlocal reject_batch
        if reject_batch:
            quarantine.write_rejects(
                conn, run_id, source, "bronze", reject_batch,
                chunk_rows=cfg.insert_chunk_rows, chunk_bytes=cfg.insert_chunk_bytes,
            )
            counters.rows_quarantined += len(reject_batch)
            reject_batch = []

    for row in itertools.chain(buffer, rest):
        try:
            out: list = []
            for i, san in enumerate(sanitized):
                v = row[i] if i < len(row) else None
                if v is not None and len(v.encode("utf-8")) > cfg.max_field_bytes:
                    raise ValueError(f"поле {san} превышает лимит {cfg.max_field_bytes} байт")
                out.append(coerce_value(v, effective[san]))
            out.extend(service)
            est = bronze_writer.estimate_row_sql(out)
            if prefix_len + est > cfg.insert_chunk_bytes:
                raise ValueError("строка превышает лимит длины запроса — не помещается в INSERT")
            if valid_batch and (
                len(valid_batch) >= cfg.insert_chunk_rows
                or valid_sql + est > cfg.insert_chunk_bytes
            ):
                flush_valid()
            valid_batch.append(out)
            valid_sql += est
        except Exception as exc:  # noqa: BLE001 — невалидная строка не роняет файл (I-8), в quarantine
            reject_batch.append(_make_reject(raw_cols, row, str(exc), cfg))
            if len(reject_batch) >= cfg.insert_chunk_rows:
                flush_rejects()

    flush_valid()
    flush_rejects()
    _log(run_id, "bronze", source=source,
         rows_ok=counters.rows_ok, rows_quarantined=counters.rows_quarantined)
    return bronze_writer.bronze_table(source), data_schema


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
    counters = _Counters()
    tables: list[str] = []
    schema_map: dict[str, dict] = {}

    try:
        size = path.stat().st_size
        if size == 0:
            raise ValueError("пустой файл (0 байт)")
        if size > cfg.max_file_bytes:
            raise ValueError(f"файл превышает лимит {cfg.max_file_bytes} байт")

        content_hash = sha256_file(path)
        prev = runlog.last_status(conn, content_hash, STAGE)
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
            table, sch = _process_source(
                conn, source, src, (run_id, content_hash, source_file), cfg, replay, counters
            )
            if table:
                tables.append(table)
                schema_map[table] = sch

        status = runlog.STATUS_PARTIAL if counters.rows_quarantined > 0 else runlog.STATUS_SUCCESS
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
            rows_ok=counters.rows_ok,
            rows_quarantined=counters.rows_quarantined,
            schema_json=json.dumps(schema_map, ensure_ascii=False) if schema_map else None,
            status=status,
            error_message=error,
        )
        try:
            runlog.record_run(conn, rec)
        except Exception as jexc:  # noqa: BLE001 — журнал не должен рушить процесс
            _log(run_id, "journal_error", error=str(jexc))

    return FileResult(path, status, counters.rows_ok, counters.rows_quarantined, tables, error)


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
