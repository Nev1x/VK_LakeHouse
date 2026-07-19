"""Единый io-адаптер доступа к Trino (переиспользуется bootstrap'ом и loader'ом 002).

Бизнес-логика не импортирует драйвер напрямую — только этот адаптер (I-4).
Креды берутся из окружения (I-7); DSN с userinfo не собирается.
"""

from __future__ import annotations

import os
import warnings

import trino
import urllib3
from trino.auth import BasicAuthentication

# Контракт namespace'ов medallion + единый quarantine (FR-006). Порядок — как в слоях данных.
MEDALLION_NAMESPACES: tuple[str, ...] = ("bronze", "silver", "gold", "quarantine")

DEFAULT_CATALOG = "iceberg"

# Публикуемый порт Trino — HTTPS с self-signed cert (password auth требует TLS, FR-015).
# Доверенный периметр = локальная машина, поэтому клиент не верифицирует cert.
warnings.simplefilter("ignore", urllib3.exceptions.InsecureRequestWarning)


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"Переменная окружения {name} не задана. "
            "Скопируй .env.example -> .env и заполни значения."
        )
    return value


def get_connection(
    *,
    catalog: str = DEFAULT_CATALOG,
    schema: str | None = None,
    request_timeout: float = 30.0,
) -> trino.dbapi.Connection:
    """DBAPI-соединение с Trino по кредам из окружения.

    host/port переопределяемы через TRINO_HOST/TRINO_PORT (по умолчанию loopback 127.0.0.1:8080,
    где host-порт 8080 маппится на HTTPS-порт контейнера 8443).
    Аутентификация — BasicAuthentication поверх HTTPS с self-signed cert и verify=False
    (password auth Trino требует TLS; доверенный периметр = локальная машина, FR-015 — уточнение
    stage-3: план закладывал HTTP, но Trino отклоняет пароль по небезопасному каналу).
    request_timeout ограничивает сетевую проверку (не зависание, I-8/NFR-001).
    """
    host = os.environ.get("TRINO_HOST", "127.0.0.1")
    port = int(os.environ.get("TRINO_PORT", "8080"))
    user = _require("TRINO_USER")
    password = _require("TRINO_PASSWORD")
    return trino.dbapi.connect(
        host=host,
        port=port,
        user=user,
        auth=BasicAuthentication(user, password),
        http_scheme="https",
        verify=False,
        catalog=catalog,
        schema=schema,
        request_timeout=request_timeout,
    )
