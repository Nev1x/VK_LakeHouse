"""Оркестрация build-gold (FR-005..FR-010): полный детерминированный пересчёт витрин из silver.

Материализация — CREATE OR REPLACE TABLE ... AS SELECT (spike: атомарно на Trino 483 —
таблица существует непрерывно, старый snapshot в истории; читатель не видит полу-состояние).
Чтение silver пиненно на snapshot (детерминизм). Общий pipeline-lock с ingest/transform (FR-009).
"""

from __future__ import annotations

import datetime as _dt
import json
import re
import sys
import uuid
from dataclasses import dataclass

from loftnav import runlog
from loftnav.config import GoldConfig
from loftnav.gold import features as features_mod
from loftnav.gold import marts as marts_mod
from loftnav.ingest.run import process_lock  # общий lock конвейера (FR-009)
from loftnav.trino_client import get_connection

STAGE = "build_gold"
_RUN_ID_RE = re.compile(r"^[a-f0-9]{32}$")

EXIT_OK = 0
EXIT_ALL_FAILED = 1
EXIT_PARTIAL = 2

# Единый реестр целей: имя → builder(run_id, small_sample, snapshot) -> MartSQL. Порядок фиксирован.
_TARGETS: dict = dict(marts_mod.MARTS)
_TARGETS[features_mod.FEATURES_NAME] = lambda rid, ss, snap: features_mod.features_sql(rid, snap)
_ALL_NAMES: tuple[str, ...] = (*marts_mod.MARTS.keys(), features_mod.FEATURES_NAME)


@dataclass
class GoldResult:
    name: str
    status: str
    rows_ok: int = 0
    error: str | None = None


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.UTC).replace(tzinfo=None)


def _log(run_id: str, step: str, **kw: object) -> None:
    parts = " ".join(f"{k}={v}" for k, v in kw.items())
    print(f"run_id={run_id} stage=build_gold step={step} {parts}", file=sys.stderr)


def _snapshot_id(conn) -> int | None:
    cur = conn.cursor()
    cur.execute(
        f"SELECT snapshot_id FROM {marts_mod.SILVER_SNAPSHOTS} "
        "ORDER BY committed_at DESC LIMIT 1"
    )
    rows = cur.fetchall()
    return int(rows[0][0]) if rows else None


def _cleanup_orphans(conn) -> None:
    """Удаляет осиротевшие временные таблицы <mart>__build_/__old_ (NFR-002).

    startswith по известным префиксам (НЕ SQL LIKE — там '_' = wildcard). При CREATE OR REPLACE
    временных таблиц не образуется; чистка защищает от легаси/крашей rename-swap.
    """
    cur = conn.cursor()
    cur.execute("SHOW TABLES FROM iceberg.gold")
    tables = [r[0] for r in cur.fetchall()]
    for t in tables:
        if any(t.startswith(f"{n}__build_") or t.startswith(f"{n}__old_") for n in _ALL_NAMES):
            drop = conn.cursor()
            drop.execute(f'DROP TABLE IF EXISTS iceberg.gold.{marts_mod.quote_ident(t)}')
            drop.fetchall()


def _build_one(conn, name: str, snapshot: int | None, gcfg: GoldConfig) -> GoldResult:
    run_id = uuid.uuid4().hex
    if not _RUN_ID_RE.fullmatch(run_id):  # инвариант перед использованием как значения (WARNING #3)
        raise RuntimeError(f"невалидный run_id: {run_id!r}")

    mart = _TARGETS[name](run_id, gcfg.small_sample, snapshot)
    started = _now()
    status = runlog.STATUS_FAILED
    err: str | None = None
    rows = 0
    try:
        ctas = (
            f"CREATE OR REPLACE TABLE {mart.target} "
            f"WITH (format = 'PARQUET', format_version = 2) AS {mart.select_sql}"
        )
        cur = conn.cursor()
        cur.execute(ctas, mart.params)
        cur.fetchall()
        cnt = conn.cursor()
        cnt.execute(f"SELECT count(*) FROM {mart.target}")
        rows = cnt.fetchall()[0][0]
        status = runlog.STATUS_SUCCESS
        _log(run_id, "built", mart=name, rows_ok=rows)
    except Exception as exc:  # noqa: BLE001 — сбой витрины не роняет остальные (I-8/NFR-002)
        err = str(exc)
        _log(run_id, "failed", mart=name, error=err)
    finally:
        _record(conn, run_id, name, mart.target, snapshot, rows, status, err, started)
    return GoldResult(name, status, rows, err)


def _record(conn, run_id, name, target, snapshot, rows, status, err, started) -> None:
    rec = runlog.RunRecord(
        run_id=run_id,
        stage=STAGE,
        started_at=started,
        finished_at=_now(),
        source_file=name,
        content_hash="none" if snapshot is None else str(snapshot),
        target_table=target,
        rows_ok=rows,
        rows_quarantined=0,
        schema_json=json.dumps({"gold_columns_version": marts_mod.GOLD_COLUMNS_VERSION}),
        status=status,
        error_message=err,
    )
    try:
        runlog.record_run(conn, rec)
    except Exception as jexc:  # noqa: BLE001 — журнал не должен рушить процесс
        _log(run_id, "journal_error", error=str(jexc))


def run_build_gold(only: str | None, gcfg: GoldConfig) -> int:
    with process_lock(gcfg):
        conn = get_connection()
        try:
            _cleanup_orphans(conn)
            snapshot = _snapshot_id(conn)
            names = [only] if only else list(_ALL_NAMES)
            if only and only not in _TARGETS:
                print(f"build-gold: неизвестная витрина {only!r} (см. {list(_ALL_NAMES)})",
                      file=sys.stderr)
                return EXIT_ALL_FAILED
            results = [_build_one(conn, n, snapshot, gcfg) for n in names]
        finally:
            conn.close()

    _print_summary(results)
    failed = [r for r in results if r.status == runlog.STATUS_FAILED]
    if not failed:
        return EXIT_OK
    if len(failed) == len(results):
        return EXIT_ALL_FAILED
    return EXIT_PARTIAL


def _print_summary(results: list[GoldResult]) -> None:
    print("\n=== build-gold summary ===")
    for r in results:
        line = f"  [{r.status:8}] {r.name}  rows_ok={r.rows_ok}"
        if r.error:
            line += f"  error={r.error}"
        print(line)
