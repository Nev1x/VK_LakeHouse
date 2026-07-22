"""Гвард-тесты additive-эволюции схемы silver (FR-001, CRITICAL-1 аудита 007). requires_stack.

Проверяют МЕХАНИЗМ `silver_writer.ensure_table` (образец bronze_writer): недостающие колонки
докатываются ALTER-ом, повтор — no-op, а MERGE поверх расширенной схемы не роняет и не теряет НИ
ОДИН источник. Тесты самодостаточны (собственная temp-таблица и явная расширенная схема) — валидны
и до пополнения `_SCHEMA` (u2), и после.
"""

from __future__ import annotations

import datetime as _dt
import uuid
from decimal import Decimal

import pytest

from loftnav.transform import silver_writer
from loftnav.trino_client import get_connection

pytestmark = pytest.mark.requires_stack

# Дельта расширения — три лофт-маркера 007 (эмуляция пополнения _SCHEMA).
_MARKERS: tuple[tuple[str, str], ...] = (
    ("ceiling_height_m", "decimal(4,2)"),
    ("wall_material", "varchar"),
    ("year_built", "bigint"),
)
# "Старый" (узкий) контракт silver — БЕЗ маркеров.
_BASE: tuple[tuple[str, str], ...] = (
    ("id", "varchar"),
    ("source", "varchar"),
    ("external_id", "varchar"),
    ("price_rub", "decimal(12,2)"),
    ("area_m2", "decimal(8,2)"),
    ("listed_at", "timestamp"),
    ("_ingested_at", "timestamp"),
)
_EXPANDED: tuple[tuple[str, str], ...] = _BASE + _MARKERS
_MARKER_NAMES = {n for n, _ in _MARKERS}
_KEYS = ("source", "external_id")
_TS = _dt.datetime(2026, 1, 1, 10, 0, 0)


def _tmp() -> str:
    return f'iceberg.silver.__u1ev_{uuid.uuid4().hex[:8]}'


def _create_base(conn, table: str) -> None:
    cols_sql = ", ".join(f'"{n}" {t}' for n, t in _BASE)
    cur = conn.cursor()
    cur.execute(f"CREATE TABLE {table} ({cols_sql}) "
                "WITH (format = 'PARQUET', format_version = 2)")
    cur.fetchall()


def _drop(conn, table: str) -> None:
    cur = conn.cursor()
    cur.execute(f"DROP TABLE IF EXISTS {table}")
    cur.fetchall()


def _q(conn, sql, params=None):
    cur = conn.cursor()
    cur.execute(sql, params) if params is not None else cur.execute(sql)
    return cur.fetchall()


def test_evolve_adds_missing_columns_and_is_idempotent() -> None:
    """(в) DESCRIBE-diff докатывает недостающие колонки; повтор — no-op, схема стабильна."""
    conn = get_connection()
    table = _tmp()
    try:
        _create_base(conn, table)
        before = silver_writer._describe_columns(conn, table)
        assert not (_MARKER_NAMES & before), "temp-таблица должна стартовать без маркеров"

        added = silver_writer._evolve_columns(conn, table, _EXPANDED)
        assert set(added) == _MARKER_NAMES              # добавлены ровно 3 недостающие
        after = silver_writer._describe_columns(conn, table)
        assert _MARKER_NAMES <= after                   # маркеры теперь в схеме

        # повтор — строго no-op (0 ALTER), схема не меняется (идемпотентность ensure)
        assert silver_writer._evolve_columns(conn, table, _EXPANDED) == []
        assert silver_writer._describe_columns(conn, table) == after
    finally:
        _drop(conn, table)
        conn.close()


def test_merge_after_expansion_preserves_all_sources() -> None:
    """(а)/(б) MERGE поверх расширенной схемы: источник с маркерами и источник БЕЗ (all-NULL) —
    оба ложатся, ни один не теряется; повторный MERGE идемпотентен и соседний источник цел."""
    conn = get_connection()
    table = _tmp()
    src_full = f"u1full_{uuid.uuid4().hex[:8]}"
    src_null = f"u1null_{uuid.uuid4().hex[:8]}"
    cols = [n for n, _ in _EXPANDED]
    types = dict(_EXPANDED)
    try:
        _create_base(conn, table)
        silver_writer._evolve_columns(conn, table, _EXPANDED)

        row_full = {
            "id": "f1", "source": src_full, "external_id": "e1",
            "price_rub": Decimal("5000000.00"), "area_m2": Decimal("50.00"),
            "listed_at": _TS, "_ingested_at": _TS,
            "ceiling_height_m": Decimal("3.20"), "wall_material": "кирпич", "year_built": 1960,
        }
        # источник без маркеров: ключи маркеров опущены → .get вернёт None (NULL)
        row_null = {
            "id": "n1", "source": src_null, "external_id": "e1",
            "price_rub": Decimal("4000000.00"), "area_m2": Decimal("40.00"),
            "listed_at": _TS, "_ingested_at": _TS,
        }

        n1 = silver_writer._merge_into(
            conn, table, cols, types, _KEYS, src_full, [row_full],
            chunk_rows=1000, chunk_bytes=700_000,
        )
        n2 = silver_writer._merge_into(
            conn, table, cols, types, _KEYS, src_null, [row_null],
            chunk_rows=1000, chunk_bytes=700_000,
        )
        assert n1 == 1 and n2 == 1

        # оба источника присутствуют — ни один не «уронил» другой
        assert _q(conn, f"SELECT count(*) FROM {table}")[0][0] == 2

        full = _q(
            conn,
            f"SELECT ceiling_height_m, wall_material, year_built FROM {table} WHERE source = ?",
            [src_full],
        )[0]
        assert full == [Decimal("3.20"), "кирпич", 1960]     # маркеры заполнены

        null = _q(
            conn,
            f"SELECT ceiling_height_m, wall_material, year_built FROM {table} WHERE source = ?",
            [src_null],
        )[0]
        assert null == [None, None, None]                     # источник без полей → NULL

        # повторный MERGE того же источника (тот же _ingested_at) — не задваивает, соседний цел
        silver_writer._merge_into(
            conn, table, cols, types, _KEYS, src_full, [row_full],
            chunk_rows=1000, chunk_bytes=700_000,
        )
        assert _q(conn, f"SELECT count(*) FROM {table}")[0][0] == 2
        assert _q(conn, f"SELECT count(*) FROM {table} WHERE source = ?", [src_null])[0][0] == 1
    finally:
        _drop(conn, table)
        conn.close()


def test_ensure_table_idempotent_on_real_silver() -> None:
    """(в) ensure_table на реальной silver — повторный вызов не меняет схему (no-op DESCRIBE)."""
    conn = get_connection()
    try:
        silver_writer.ensure_table(conn)
        before = _q(conn, f"DESCRIBE {silver_writer.SILVER_TABLE}")
        silver_writer.ensure_table(conn)
        after = _q(conn, f"DESCRIBE {silver_writer.SILVER_TABLE}")
        assert before == after
    finally:
        conn.close()
