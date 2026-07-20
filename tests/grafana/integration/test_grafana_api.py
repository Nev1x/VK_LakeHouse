"""Интеграционные тесты Grafana HTTP API (FR-009). Маркер requires_stack.

Кредами admin из env: datasource присутствует и health OK против trino:8443, оба дашборда
провижинятся, плагин установлен. Браузерную визуалку делает отдельный QA.
"""

from __future__ import annotations

import os

import pytest
import requests

pytestmark = pytest.mark.requires_stack

_TIMEOUT = 30


def _base() -> str:
    return f"http://127.0.0.1:{os.environ.get('GRAFANA_PORT', '3000')}"


def _auth() -> tuple[str, str]:
    return (os.environ["GRAFANA_ADMIN_USER"], os.environ["GRAFANA_ADMIN_PASSWORD"])


def _get(path: str):
    return requests.get(f"{_base()}{path}", auth=_auth(), timeout=_TIMEOUT)


def test_trino_datasource_present() -> None:
    resp = _get("/api/datasources")
    assert resp.status_code == 200
    types = {d["type"] for d in resp.json()}
    assert "trino-datasource" in types
    # детали (basicAuthUser с подставленным env) — через uid-эндпоинт (list их не отдаёт)
    ds = _get("/api/datasources/uid/loftnav-trino").json()
    assert ds["url"] == "https://trino:8443"
    assert ds["basicAuthUser"] == os.environ["TRINO_USER"]  # env подставлен, не литерал


def test_datasource_health_ok() -> None:
    """/api/datasources/uid/<uid>/health = OK против trino:8443 (не просто curl 200)."""
    resp = _get("/api/datasources/uid/loftnav-trino/health")
    assert resp.status_code == 200, resp.text
    assert resp.json().get("status") == "OK", resp.text


def test_both_dashboards_provisioned() -> None:
    resp = _get("/api/search?type=dash-db")
    assert resp.status_code == 200
    uids = {d["uid"] for d in resp.json()}
    assert "loftnav-platform-ops" in uids
    assert "loftnav-apartments" in uids


def test_plugin_installed() -> None:
    resp = _get("/api/plugins/trino-datasource/settings")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body.get("id") == "trino-datasource"
    assert body.get("info", {}).get("version") == "1.0.11"
