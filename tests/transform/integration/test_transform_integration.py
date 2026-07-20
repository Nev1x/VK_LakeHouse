"""Интеграционные тесты transform на живом стеке (FR-006..FR-011, FR-015). Маркер requires_stack.

Источники именуются уникально (uuid): journal/идемпотентность глобальны по content_hash.
Каждый тест убирает свои таблицы/партицию silver за собой.
"""

from __future__ import annotations

import dataclasses
import tempfile
import time
import uuid
from decimal import Decimal
from pathlib import Path

import pytest

from loftnav.config import IngestConfig, TransformConfig
from loftnav.ingest.run import ingest_paths
from loftnav.transform import silver_writer
from loftnav.transform.run import EXIT_ALL_FAILED, EXIT_OK, run_transform
from loftnav.trino_client import get_connection

pytestmark = pytest.mark.requires_stack


def _q(sql: str, params=None):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, params) if params is not None else cur.execute(sql)
        return cur.fetchall()
    finally:
        conn.close()


def _scount(source: str) -> int:
    sql = f"SELECT count(*) FROM {silver_writer.SILVER_TABLE} WHERE source = ?"
    return _q(sql, [source])[0][0]


def _ingest_csv(content: str, source: str) -> None:
    # ingest идемпотентен ГЛОБАЛЬНО по content_hash — делаем контент уникальным (tag-колонка).
    lines = content.strip().split("\n")
    header, rows = lines[0], lines[1:]
    sep = ";" if ";" in header else ","
    header = header + sep + "tag_col"
    rows = [r + sep + source for r in rows]
    d = Path(tempfile.mkdtemp())
    f = d / f"{source}.csv"
    f.write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")
    ingest_paths([f], source, IngestConfig.from_env())


def _tcfg(mapping_dir: Path) -> TransformConfig:
    return dataclasses.replace(TransformConfig.from_env(), mapping_dir=mapping_dir)


def _write_config(mapping_dir: Path, source: str, body: str) -> None:
    mapping_dir.mkdir(parents=True, exist_ok=True)
    (mapping_dir / f"{source}.toml").write_text(body, encoding="utf-8")


def _cleanup(source: str) -> None:
    conn = get_connection()
    try:
        cur = conn.cursor()
        for sql in (
            f'DROP TABLE IF EXISTS iceberg.bronze."{source}"',
            f'DROP TABLE IF EXISTS iceberg.quarantine."silver_{source}_rejects"',
            f"DELETE FROM {silver_writer.SILVER_TABLE} WHERE source = ?",
        ):
            cur.execute(sql, [source]) if "DELETE" in sql else cur.execute(sql)
            cur.fetchall()
    finally:
        conn.close()


_CONFIG = """
[meta]
external_id = "id"
[fields.price_rub]
input = "price"
cast = "decimal"
unit_convert = { from = "thousands_rub", to = "rub" }
[fields.area_m2]
input = "area"
regex_replace = { pattern = ",", replacement = "." }
cast = "decimal"
[fields.rooms]
input = "rooms"
cast = "bigint"
"""


def test_normalize_types_and_incremental(tmp_path: Path) -> None:
    """Источник → silver с DECIMAL-ценой в рублях; повтор → 0 партий (FR-003/FR-007, крит.1/2)."""
    src = f"itx_{uuid.uuid4().hex[:8]}"
    _ingest_csv("id;price;area;rooms\n1;5000;45,5;2\n2;7200;60,0;3\n", src)
    _write_config(tmp_path, src, _CONFIG)
    tcfg = _tcfg(tmp_path)
    try:
        assert run_transform(src, None, tcfg) == EXIT_OK
        rows = _q(
            "SELECT external_id, price_rub, area_m2, rooms FROM "
            f"{silver_writer.SILVER_TABLE} WHERE source = ? ORDER BY external_id", [src]
        )
        assert rows == [["1", Decimal("5000000.00"), Decimal("45.50"), 2],
                        ["2", Decimal("7200000.00"), Decimal("60.00"), 3]]
        # инкрементальность: повтор -> 0 партий, count стабилен
        assert run_transform(src, None, tcfg) == EXIT_OK
        assert _scount(src) == 2  # count стабилен, 0 новых партий
    finally:
        _cleanup(src)


def test_merge_update_price(tmp_path: Path) -> None:
    """Переингест изменённой цены того же external_id → MERGE-update, без дубля (FR-006, крит.3)."""
    src = f"itm_{uuid.uuid4().hex[:8]}"
    _ingest_csv("id;price;area;rooms\n1;5000;45,5;2\n", src)
    _write_config(tmp_path, src, _CONFIG)
    tcfg = _tcfg(tmp_path)
    try:
        run_transform(src, None, tcfg)
        assert _q(f"SELECT price_rub FROM {silver_writer.SILVER_TABLE} WHERE source=?", [src]) == [
            [Decimal("5000000.00")]
        ]
        _ingest_csv("id;price;area;rooms\n1;6000;45,5;2\n", src)  # новый content_hash
        run_transform(src, None, tcfg)
        rows = _q(
            "SELECT external_id, price_rub FROM "
            f"{silver_writer.SILVER_TABLE} WHERE source = ?", [src]
        )
        assert rows == [["1", Decimal("6000000.00")]]  # обновлено, не задвоено
    finally:
        _cleanup(src)


def test_quarantine_balances(tmp_path: Path) -> None:
    """Битая строка (цена 0) → silver_*_rejects; rows_ok+rows_q = источник (FR-009, крит.4)."""
    src = f"itq_{uuid.uuid4().hex[:8]}"
    _ingest_csv("id;price;area;rooms\n1;5000;45,5;2\n2;0;60,0;3\n", src)  # строка 2 -> reject
    _write_config(tmp_path, src, _CONFIG)
    try:
        run_transform(src, None, _tcfg(tmp_path))
        silver = _scount(src)
        rej = _q(f'SELECT count(*), min(reason) FROM iceberg.quarantine."silver_{src}_rejects"')[0]
        assert silver == 1 and rej[0] == 1
        assert "sanity" in rej[1]
        assert silver + rej[0] == 2  # = строки источника
    finally:
        _cleanup(src)


def test_skip_without_config(tmp_path: Path) -> None:
    """Bronze-источник без конфига → journal skipped, НЕ quarantine (FR-010, крит.6)."""
    src = f"its_{uuid.uuid4().hex[:8]}"
    _ingest_csv("id;price;area\n1;5000;45,5\n", src)
    try:
        run_transform(src, None, _tcfg(tmp_path))  # пустой mapping_dir -> нет конфига
        st = _q(
            "SELECT status FROM iceberg.ops.pipeline_runs "
            "WHERE stage='transform' AND source_file=? ORDER BY started_at DESC LIMIT 1", [src]
        )
        assert st and st[0][0] == "skipped"
        assert _scount(src) == 0
    finally:
        _cleanup(src)


def test_config_nonexistent_column(tmp_path: Path) -> None:
    """Конфиг ссылается на несуществующую bronze-колонку → failed с именем колонки (FR-002)."""
    src = f"itc_{uuid.uuid4().hex[:8]}"
    _ingest_csv("id;price;area\n1;5000;45,5\n", src)
    _write_config(
        tmp_path, src,
        '[meta]\nexternal_id="id"\n[fields.price_rub]\ninput="nonexistent"\ncast="decimal"\n'
        '[fields.area_m2]\ninput="area"\ncast="decimal"\n',
    )
    try:
        assert run_transform(src, None, _tcfg(tmp_path)) == EXIT_ALL_FAILED
        st = _q(
            "SELECT status, error_message FROM iceberg.ops.pipeline_runs "
            "WHERE stage='transform' AND source_file=? ORDER BY started_at DESC LIMIT 1", [src]
        )[0]
        assert st[0] == "failed" and "nonexistent" in st[1]
    finally:
        _cleanup(src)


def test_reprocess_clears_quarantine(tmp_path: Path) -> None:
    """Двойной --reprocess → reject-строки НЕ задваиваются (quarantine чистится, WARNING-1)."""
    src = f"itrq_{uuid.uuid4().hex[:8]}"
    _ingest_csv("id;price;area;rooms\n1;5000;45,5;2\n2;0;60,0;3\n", src)  # строка 2 -> reject
    _write_config(tmp_path, src, _CONFIG)
    tcfg = _tcfg(tmp_path)
    rej_sql = f'SELECT count(*) FROM iceberg.quarantine."silver_{src}_rejects"'
    try:
        run_transform(src, None, tcfg)
        assert _q(rej_sql)[0][0] == 1
        run_transform(None, src, tcfg)   # --reprocess #1
        assert _q(rej_sql)[0][0] == 1    # не 2
        run_transform(None, src, tcfg)   # --reprocess #2
        assert _q(rej_sql)[0][0] == 1    # не 3
    finally:
        _cleanup(src)


def test_reprocess_only_target_source(tmp_path: Path) -> None:
    """--reprocess <A> трогает ТОЛЬКО источник A, не B (INFO-2)."""
    a = f"ita_{uuid.uuid4().hex[:8]}"
    b = f"itb_{uuid.uuid4().hex[:8]}"
    for s in (a, b):
        _ingest_csv("id;price;area;rooms\n1;5000;45,5;2\n", s)
        _write_config(tmp_path, s, _CONFIG)
    tcfg = _tcfg(tmp_path)
    cnt_sql = (
        "SELECT count(*) FROM iceberg.ops.pipeline_runs "
        "WHERE stage='transform' AND source_file=?"
    )
    try:
        run_transform(None, None, tcfg)          # обработать оба
        b_before = _q(cnt_sql, [b])[0][0]
        run_transform(None, a, tcfg)             # --reprocess A
        assert _q(cnt_sql, [b])[0][0] == b_before  # у B новых журнальных записей нет
    finally:
        _cleanup(a)
        _cleanup(b)


def test_regex_timeout_quarantine(tmp_path: Path) -> None:
    """Патологический regex на коротком значении → reject timeout, не висит (CRITICAL-1)."""
    src = f"itg_{uuid.uuid4().hex[:8]}"
    long_a = "a" * 30 + "!"       # < cap, но catastrophic backtracking для (a+)+$
    _ingest_csv(f"id;price;area;rooms;code\n1;5000;45,5;2;{long_a}\n2;7200;60,0;3;x\n", src)
    _write_config(
        tmp_path, src,
        _CONFIG + '[fields.district]\ninput = "code"\n'
        'regex_replace = { pattern = "(a+)+$", replacement = "z" }\n',
    )
    tcfg = dataclasses.replace(_tcfg(tmp_path), regex_timeout_sec=0.5)
    start = time.monotonic()
    try:
        assert run_transform(src, None, tcfg) == EXIT_OK
        assert time.monotonic() - start < 15  # не подвис (иначе держал бы lock)
        silver = _scount(src)
        rej = _q(f'SELECT count(*), min(reason) FROM iceberg.quarantine."silver_{src}_rejects"')[0]
        assert silver == 1 and rej[0] == 1          # строка 2 (code=x) ок, строка 1 — timeout
        assert "уложился" in rej[1] or "regex" in rej[1].lower()
    finally:
        _cleanup(src)


def test_reprocess_after_config_change(tmp_path: Path) -> None:
    """Смена конфига → стоп с подсказкой; --reprocess → переигровка (FR-008, крит.5)."""
    src = f"itr_{uuid.uuid4().hex[:8]}"
    _ingest_csv("id;price;area;rooms\n1;5000;45,5;2\n", src)
    _write_config(tmp_path, src, _CONFIG)
    tcfg = _tcfg(tmp_path)
    try:
        run_transform(src, None, tcfg)
        _write_config(tmp_path, src, _CONFIG + "\n# edit\n")  # новый config_hash
        assert run_transform(src, None, tcfg) == EXIT_ALL_FAILED   # стоп
        st = _q(
            "SELECT status, error_message FROM iceberg.ops.pipeline_runs "
            "WHERE stage='transform' AND source_file=? ORDER BY started_at DESC LIMIT 1", [src]
        )[0]
        assert st[0] == "failed" and "reprocess" in st[1]
        assert run_transform(None, src, tcfg) == EXIT_OK           # --reprocess переигрывает
        assert _scount(src) == 1
    finally:
        _cleanup(src)
