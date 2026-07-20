"""Оркестрация transform (FR-006..FR-011): bronze-партиции → apartments_clean (MERGE upsert).

Инкрементальность по журналу stage='transform' (anti-join); reprocess при смене конфига;
источник без конфига → skipped; сбой посреди — честные счётчики. Единый lock с ingest (FR-012).
Значения — bind-параметры; идентификаторы — ident; чтение bronze — fetchmany (T5).
"""

from __future__ import annotations

import datetime as _dt
import json
import sys
import uuid
from dataclasses import dataclass

from loftnav import quarantine, runlog
from loftnav.config import SANITY_DEFAULTS, TransformConfig
from loftnav.ident import quote_ident
from loftnav.ingest.run import process_lock  # общий lock конвейера (FR-012)
from loftnav.transform import dedup, silver_writer
from loftnav.transform.mapping import Mapping, MappingError, load_mapping, validate_against_bronze
from loftnav.transform.normalize import NormalizationError, sanity_ok
from loftnav.trino_client import get_connection

STAGE = "transform"
SILVER_TABLE = silver_writer.SILVER_TABLE

EXIT_OK = 0
EXIT_ALL_FAILED = 1
EXIT_PARTIAL = 2

# обязательные поля silver — их отсутствие после нормализации → строка в quarantine (FR-003)
_MANDATORY = ("price_rub", "area_m2")


@dataclass
class SourceResult:
    source: str
    status: str
    rows_ok: int = 0
    rows_quarantined: int = 0
    partitions: int = 0
    error: str | None = None


class ConfigChanged(Exception):
    """Хэш конфига источника изменился — нужен явный --reprocess (FR-008)."""


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.UTC).replace(tzinfo=None)


def _log(run_id: str, step: str, **kw: object) -> None:
    parts = " ".join(f"{k}={v}" for k, v in kw.items())
    print(f"run_id={run_id} stage=transform step={step} {parts}", file=sys.stderr)


def _bronze_table(source: str) -> str:
    return f"iceberg.bronze.{quote_ident(source)}"


def _bronze_columns(conn, source: str) -> set[str]:
    cur = conn.cursor()
    cur.execute(f"DESCRIBE {_bronze_table(source)}")
    return {r[0] for r in cur.fetchall()}


def _distinct_hashes(conn, source: str) -> list[str]:
    cur = conn.cursor()
    cur.execute(f"SELECT DISTINCT _content_hash FROM {_bronze_table(source)}")
    return [r[0] for r in cur.fetchall() if r[0]]


def _last_config_hash(conn, source: str) -> str | None:
    cur = conn.cursor()
    cur.execute(
        "SELECT schema_json FROM iceberg.ops.pipeline_runs "
        "WHERE stage = ? AND source_file = ? AND status = 'success' "
        "ORDER BY started_at DESC LIMIT 1",
        [STAGE, source],
    )
    rows = cur.fetchall()
    if not rows or not rows[0][0]:
        return None
    try:
        return json.loads(rows[0][0]).get("mapping_config_hash")
    except (ValueError, TypeError):
        return None


def _bronze_sources(conn) -> list[str]:
    cur = conn.cursor()
    cur.execute("SHOW TABLES FROM iceberg.bronze")
    return sorted(r[0] for r in cur.fetchall())


def _normalize_row(
    rec: dict, mapping: Mapping, source: str, run_id: str, cap: int
) -> dict:
    """bronze-строка → silver-строка. NormalizationError/ValueError → строка в quarantine."""
    silver: dict[str, object] = dict.fromkeys(silver_writer.ALL_COLUMNS)

    if mapping.external_id_column:
        ext = rec.get(mapping.external_id_column)
        ext = None if ext is None else str(ext)
        if not ext:
            raise NormalizationError("external_id пуст при заданном в конфиге столбце")
    else:
        ext = None  # синтетический ниже, после нормализации полей

    for field_name, spec in mapping.fields.items():
        raw = rec.get(spec.input) if spec.input else None
        raw = None if raw is None else str(raw)
        val = spec.apply(raw, cap)
        if not sanity_ok(field_name, val, SANITY_DEFAULTS):
            raise NormalizationError(f"поле {field_name}={val!r} вне sanity-диапазона")
        silver[field_name] = val

    for field_name in _MANDATORY:
        if silver[field_name] is None:
            raise NormalizationError(f"обязательное поле {field_name} пусто после нормализации")

    if ext is None:  # best-effort синтетика (FR-005): хэш нормализованных доменных полей
        basis = ";".join(f"{k}={silver[k]}" for k in sorted(silver_writer.MAPPABLE_FIELDS))
        ext = dedup.make_id(source, basis)

    silver["source"] = source
    silver["external_id"] = ext
    silver["id"] = dedup.make_id(source, ext)
    silver["_source_run_id"] = rec.get("_run_id")
    silver["_source_content_hash"] = rec.get("_content_hash")
    silver["_mapping_config_hash"] = mapping.config_hash
    silver["_ingested_at"] = rec.get("_ingested_at")
    silver["_transformed_at"] = _now()
    silver["_transform_run_id"] = run_id
    return silver


def _process_partition(conn, source, content_hash, mapping, run_id, tcfg) -> tuple[int, int]:
    """Читает bronze (fetchmany), нормализует, дедупит, MERGE в silver, rejects. Отдаёт (ok, q)."""
    cur = conn.cursor()
    cur.execute(
        f"SELECT * FROM {_bronze_table(source)} WHERE _content_hash = ?", [content_hash]
    )
    cols = [d[0] for d in cur.description]
    silver_rows: list[dict] = []
    rejects: list[quarantine.Reject] = []
    while True:
        batch = cur.fetchmany(tcfg.read_chunk_rows)
        if not batch:
            break
        for row in batch:
            rec = dict(zip(cols, row, strict=True))
            try:
                silver_rows.append(
                    _normalize_row(rec, mapping, source, run_id, tcfg.regex_value_cap)
                )
            except (NormalizationError, ValueError) as exc:
                raw = json.dumps(rec, ensure_ascii=False, default=str)[: tcfg.regex_value_cap]
                rejects.append(quarantine.Reject(raw_record=raw, reason=str(exc)))

    deduped = dedup.dedup_latest(silver_rows)
    ok = silver_writer.merge_rows(
        conn, source, deduped,
        chunk_rows=tcfg.merge_chunk_rows, chunk_bytes=tcfg.merge_chunk_bytes,
    )
    q = quarantine.write_rejects(
        conn, run_id, source, "silver", rejects,
        chunk_rows=tcfg.merge_chunk_rows, chunk_bytes=tcfg.merge_chunk_bytes,
    )
    _log(run_id, "partition", source=source, content_hash=content_hash[:12], rows_ok=ok, rejects=q)
    return ok, q


def _transform_one(conn, source: str, reprocess: bool, tcfg: TransformConfig) -> SourceResult:
    run_id = uuid.uuid4().hex
    config_path = tcfg.mapping_dir / f"{source}.toml"

    if not config_path.exists():
        _record(conn, run_id, source, "(no-config)", runlog.STATUS_SKIPPED, 0, 0, None, None)
        _log(run_id, "skip", source=source, reason="no-mapping-config")
        return SourceResult(source, runlog.STATUS_SKIPPED)

    try:
        mapping = load_mapping(config_path)
        bronze_cols = _bronze_columns(conn, source)
        for warn in validate_against_bronze(mapping, bronze_cols):
            _log(run_id, "warn", source=source, msg=warn)

        last_hash = _last_config_hash(conn, source)
        if reprocess:
            silver_writer.delete_source(conn, source)
            partitions = _distinct_hashes(conn, source)
            _log(run_id, "reprocess", source=source, partitions=len(partitions))
        else:
            if last_hash is not None and last_hash != mapping.config_hash:
                raise ConfigChanged(
                    f"конфиг источника {source} изменился — запусти: "
                    f"loftnav transform --reprocess {source}"
                )
            # partial терминален для transform: MERGE идемпотентен, но re-run копил бы quarantine
            # и ломал бы идемпотентность (0 партий на повторе). Переобрабатывается только failed.
            _done = (runlog.STATUS_SUCCESS, runlog.STATUS_SKIPPED, runlog.STATUS_PARTIAL)
            partitions = [
                h for h in _distinct_hashes(conn, source)
                if runlog.last_status(conn, h, STAGE) not in _done
            ]
    except (MappingError, ConfigChanged) as exc:
        _record(conn, run_id, source, "(config)", runlog.STATUS_FAILED, 0, 0, None, str(exc))
        _log(run_id, "failed", source=source, error=str(exc))
        return SourceResult(source, runlog.STATUS_FAILED, error=str(exc))

    schema_json = json.dumps(
        {
            "mapping_config_hash": mapping.config_hash,
            "silver_columns_version": silver_writer.SILVER_COLUMNS_VERSION,
            "source": source,
        }
    )
    total_ok = total_q = 0
    for content_hash in partitions:
        started = _now()
        status = runlog.STATUS_FAILED
        err: str | None = None
        ok = q = 0
        try:
            ok, q = _process_partition(conn, source, content_hash, mapping, run_id, tcfg)
            status = runlog.STATUS_PARTIAL if q > 0 else runlog.STATUS_SUCCESS
        except Exception as exc:  # noqa: BLE001 — сбой партии не роняет остальные (I-8)
            err = str(exc)
            _log(run_id, "partition_failed", source=source, error=err)
        finally:
            _record(
                conn, run_id, source, content_hash, status, ok, q, schema_json, err,
                started=started,
            )
        total_ok += ok
        total_q += q

    status = runlog.STATUS_PARTIAL if total_q > 0 else runlog.STATUS_SUCCESS
    return SourceResult(source, status, total_ok, total_q, len(partitions))


def _record(conn, run_id, source, content_hash, status, ok, q, schema_json, err, *, started=None):
    now = _now()
    rec = runlog.RunRecord(
        run_id=run_id,
        stage=STAGE,
        started_at=started or now,
        finished_at=now,
        source_file=source,
        content_hash=content_hash,
        target_table=SILVER_TABLE,
        rows_ok=ok,
        rows_quarantined=q,
        schema_json=schema_json,
        status=status,
        error_message=err,
    )
    try:
        runlog.record_run(conn, rec)
    except Exception as jexc:  # noqa: BLE001 — журнал не должен рушить процесс
        _log(run_id, "journal_error", error=str(jexc))


def run_transform(
    source_filter: str | None, reprocess: str | None, tcfg: TransformConfig
) -> int:
    with process_lock(tcfg):
        conn = get_connection()
        try:
            silver_writer.ensure_table(conn)
            sources = _bronze_sources(conn)
            if source_filter:
                sources = [s for s in sources if s == source_filter]
            if reprocess and reprocess not in sources:
                sources.append(reprocess)
            results = [
                _transform_one(conn, s, reprocess == s, tcfg) for s in sources
            ]
        finally:
            conn.close()

    _print_summary(results)
    failed = [r for r in results if r.status == runlog.STATUS_FAILED]
    if not failed:
        return EXIT_OK
    if len(failed) == len(results):
        return EXIT_ALL_FAILED
    return EXIT_PARTIAL


def _print_summary(results: list[SourceResult]) -> None:
    print("\n=== transform summary ===")
    for r in results:
        line = (
            f"  [{r.status:8}] {r.source}  ok={r.rows_ok} quarantined={r.rows_quarantined} "
            f"partitions={r.partitions}"
        )
        if r.error:
            line += f"  error={r.error}"
        print(line)
