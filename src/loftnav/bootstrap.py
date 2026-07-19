"""Идемпотентный bootstrap namespace'ов medallion в каталоге Iceberg (FR-006).

Создаёт схемы iceberg.bronze / silver / gold / quarantine (CREATE SCHEMA IF NOT EXISTS).
Резервирует ИМЕНА контрактов для фич 002-006; таблицы слоёв создают сами эти фичи.
Запуск: python -m loftnav.bootstrap (стек должен быть поднят).
"""

from __future__ import annotations

import sys
import time

from loftnav.trino_client import MEDALLION_NAMESPACES, get_connection


def _wait_ready(timeout: float = 60.0, backoff: float = 3.0) -> None:
    """Ждёт готовности Trino к аутентифицированным запросам.

    Healthcheck /v1/info зеленеет раньше, чем догружаются password-аутентификаторы
    (гонка старта) — первый auth-запрос может вернуть 500. Ретраим до готовности (I-8).
    """
    deadline = time.monotonic() + timeout
    last: Exception | None = None
    while time.monotonic() < deadline:
        try:
            conn = get_connection()
            try:
                cur = conn.cursor()
                cur.execute("SELECT 1")
                cur.fetchall()
                return
            finally:
                conn.close()
        except Exception as exc:  # noqa: BLE001 — ждём прогрева, любой транзиент ретраим
            last = exc
            time.sleep(backoff)
    raise RuntimeError(f"Trino не готов к запросам за {timeout:.0f}s: {last}")


def ensure_namespaces(namespaces: tuple[str, ...] = MEDALLION_NAMESPACES) -> list[str]:
    """Идемпотентно создаёт namespace'ы; возвращает список созданных/подтверждённых схем."""
    _wait_ready()
    conn = get_connection()
    created: list[str] = []
    try:
        cur = conn.cursor()
        for ns in namespaces:
            # Имена из фиксированного кортежа-контракта, не пользовательский ввод (I-7).
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS iceberg.{ns}")
            cur.fetchall()
            created.append(ns)
    finally:
        conn.close()
    return created


def main() -> int:
    try:
        created = ensure_namespaces()
    except Exception as exc:  # noqa: BLE001 — на CLI показываем понятную причину, не трейс наружу
        print(f"bootstrap: ошибка создания namespace'ов: {exc}", file=sys.stderr)
        return 1
    print("bootstrap: namespace'ы готовы: " + ", ".join(f"iceberg.{n}" for n in created))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
