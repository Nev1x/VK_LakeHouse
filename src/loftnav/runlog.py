"""Append-only журнал прогонов iceberg.ops.pipeline_runs (FR-009, I-3; общий для 002/003/006).

ОДИН INSERT на прогон файла (в try/finally оркестратора); НИКАКИХ UPDATE. Значения — bind-параметры.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass

OPS_TABLE = "iceberg.ops.pipeline_runs"

# Статусы (FR-009).
STATUS_SUCCESS = "success"
STATUS_PARTIAL = "partial"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"

_CREATE = f"""CREATE TABLE IF NOT EXISTS {OPS_TABLE} (
    run_id varchar,
    stage varchar,
    started_at timestamp,
    finished_at timestamp,
    source_file varchar,
    content_hash varchar,
    target_table varchar,
    rows_ok bigint,
    rows_quarantined bigint,
    schema_json varchar,
    status varchar,
    error_message varchar
) WITH (format = 'PARQUET', format_version = 2)"""


@dataclass
class RunRecord:
    run_id: str
    stage: str
    started_at: _dt.datetime
    finished_at: _dt.datetime
    source_file: str
    content_hash: str
    target_table: str | None
    rows_ok: int
    rows_quarantined: int
    schema_json: str | None
    status: str
    error_message: str | None


def ensure_table(conn) -> None:
    cur = conn.cursor()
    cur.execute(_CREATE)
    cur.fetchall()


def record_run(conn, rec: RunRecord) -> None:
    """Единственный INSERT записи прогона (append-only). Все значения — bind-параметры (I-7)."""
    cur = conn.cursor()
    cur.execute(
        f"INSERT INTO {OPS_TABLE} (run_id, stage, started_at, finished_at, source_file, "
        "content_hash, target_table, rows_ok, rows_quarantined, schema_json, status, "
        "error_message) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            rec.run_id,
            rec.stage,
            rec.started_at,
            rec.finished_at,
            rec.source_file,
            rec.content_hash,
            rec.target_table,
            rec.rows_ok,
            rec.rows_quarantined,
            rec.schema_json,
            rec.status,
            rec.error_message,
        ],
    )
    cur.fetchall()


def last_status(conn, content_hash: str) -> str | None:
    """Последний по времени статус прогона для данного content_hash (идемпотентность FR-010)."""
    cur = conn.cursor()
    cur.execute(
        f"SELECT status FROM {OPS_TABLE} WHERE content_hash = ? "
        "ORDER BY started_at DESC LIMIT 1",
        [content_hash],
    )
    rows = cur.fetchall()
    return rows[0][0] if rows else None
