"""Smoke: доказательство работоспособности цепочки Trino -> Iceberg (JDBC) -> MinIO (FR-010, I-13).

Не «контейнеры запущены», а реальный round-trip: создать таблицу, записать, прочитать,
СРАВНИТЬ значения, убрать за собой. При недоступности сервиса — понятная ошибка с таймаутом.
"""

from __future__ import annotations

import os
import uuid

import pytest
import requests
import urllib3

from loftnav.trino_client import get_connection

_HTTP_TIMEOUT = 30  # NFR-001: каждая сетевая проверка smoke <= 30s

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _host_url(scheme: str, port_env: str, default_port: str, path: str) -> str:
    port = os.environ.get(port_env, default_port)
    return f"{scheme}://127.0.0.1:{port}{path}"


def test_services_liveness() -> None:
    """Liveness опубликованных сервисов (US-5). Postgres проверяется косвенно round-trip'ом."""
    # (url, verify) — Trino публикуется по HTTPS (self-signed), MinIO/Grafana по HTTP.
    checks = {
        "minio": (_host_url("http", "MINIO_API_PORT", "9000", "/minio/health/ready"), True),
        "trino": (_host_url("https", "TRINO_PORT", "8080", "/v1/info"), False),
        "grafana": (_host_url("http", "GRAFANA_PORT", "3000", "/api/health"), True),
    }
    for name, (url, verify) in checks.items():
        try:
            resp = requests.get(url, timeout=_HTTP_TIMEOUT, verify=verify)
        except requests.RequestException as exc:
            pytest.fail(f"{name}: сервис недоступен ({url}): {exc}")
        assert resp.status_code == 200, f"{name}: {url} вернул {resp.status_code}"


def test_iceberg_roundtrip(retry) -> None:
    """SHOW CATALOGS -> CREATE SCHEMA/TABLE -> INSERT -> SELECT со сравнением -> cleanup."""
    table = f"smoke_{uuid.uuid4().hex[:8]}"
    expected = [(1, "loft"), (2, "not-loft"), (3, "warehouse")]

    conn = get_connection()
    try:
        cur = conn.cursor()

        # (2) каталог iceberg присутствует — с ретраем на ленивую инициализацию
        catalogs = retry(lambda: _fetch(cur, "SHOW CATALOGS"))
        assert any(row[0] == "iceberg" for row in catalogs), f"iceberg нет в {catalogs}"

        # (3) namespace + таблица (idempotent schema)
        _fetch(cur, "CREATE SCHEMA IF NOT EXISTS iceberg.smoke")
        _fetch(cur, f"CREATE TABLE iceberg.smoke.{table} (id integer, val varchar)")

        # (4) запись
        _fetch(
            cur,
            f"INSERT INTO iceberg.smoke.{table} VALUES "
            "(1, 'loft'), (2, 'not-loft'), (3, 'warehouse')",
        )

        # (5) чтение обратно + СРАВНЕНИЕ значений (round-trip, не «запрос не упал»)
        rows = _fetch(cur, f"SELECT id, val FROM iceberg.smoke.{table} ORDER BY id")
        assert [(r[0], r[1]) for r in rows] == expected, f"round-trip mismatch: {rows}"
    finally:
        # (6) cleanup за собой — таблица и schema smoke
        try:
            cleanup = conn.cursor()
            _fetch(cleanup, f"DROP TABLE IF EXISTS iceberg.smoke.{table}")
            _fetch(cleanup, "DROP SCHEMA IF EXISTS iceberg.smoke")
        finally:
            conn.close()


def test_missing_env_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Отсутствующая env -> понятная ошибка, не тихий литерал креда (SEC-2, T8)."""
    monkeypatch.delenv("TRINO_USER", raising=False)
    monkeypatch.delenv("TRINO_PASSWORD", raising=False)
    with pytest.raises(RuntimeError, match="TRINO_USER"):
        get_connection()


def _fetch(cursor, sql: str):
    cursor.execute(sql)
    return cursor.fetchall()
