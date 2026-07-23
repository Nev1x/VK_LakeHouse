"""Юнит-тесты дашбордов-как-код (FR-003/FR-004/FR-005): структура, datasource-by-name, bounded."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_DASH = Path(__file__).resolve().parents[3] / "infra" / "grafana" / "provisioning" / "dashboards"
_FILES = ("platform-ops.json", "apartments.json")


def _load(name: str) -> dict:
    return json.loads((_DASH / name).read_text(encoding="utf-8"))


def _iter_datasource_refs(dash: dict):
    for panel in dash.get("panels", []):
        yield panel.get("datasource")
        for t in panel.get("targets", []):
            yield t.get("datasource")
    for var in dash.get("templating", {}).get("list", []):
        if var.get("type") != "datasource":  # сама datasource-переменная ссылается по type, не uid
            yield var.get("datasource")


def _iter_sql(dash: dict):
    # ключ строго rawSQL: фронтенд trino-плагина подставляет переменные только в это поле;
    # Go-бэкенд читает JSON без учёта регистра, поэтому rawSql «работал»,
    # но ${var} уезжал в Trino сырым
    for panel in dash.get("panels", []):
        for t in panel.get("targets", []):
            assert "rawSql" not in t, f"{panel['title']}: rawSql → rawSQL (интерполяция)"
            if t.get("rawSQL"):
                yield panel["title"], t["rawSQL"]


@pytest.mark.parametrize("name", _FILES)
def test_dashboard_structure(name) -> None:
    d = _load(name)
    assert d["schemaVersion"] >= 30
    assert d["title"] and d["uid"].startswith("loftnav-")
    assert len(d["panels"]) >= 3


@pytest.mark.parametrize("name", _FILES)
def test_refresh_off_or_slow(name) -> None:
    """Auto-refresh off ("") или ≥5м (NFR-006 bounded-нагрузка)."""
    refresh = _load(name).get("refresh", "")
    assert refresh == "" or refresh in ("5m", "10m", "15m", "30m", "1h")


@pytest.mark.parametrize("name", _FILES)
def test_datasource_by_variable_not_hardcoded_uid(name) -> None:
    """ВСЕ datasource-ссылки — через ${DS_TRINO}, не хардкоженный uid (FR-005)."""
    for ref in _iter_datasource_refs(_load(name)):
        if ref is None:
            continue
        uid = ref.get("uid") if isinstance(ref, dict) else ref
        assert uid == "${DS_TRINO}", f"datasource должен быть ${{DS_TRINO}}, а не {uid!r}"


def test_ops_journal_panels_bounded() -> None:
    """КАЖДАЯ панель pipeline_runs — bounded time-range; лента failed — ещё и LIMIT (T4)."""
    for title, sql in _iter_sql(_load("platform-ops.json")):
        if "pipeline_runs" not in sql:
            continue  # information_schema-панель bounded by construction
        assert "$__timeFrom()" in sql or "$__timeFilter" in sql, f"панель {title!r} без time-bound"
        # лента сырых прогонов (error_message без агрегации) обязана иметь LIMIT
        if "error_message" in sql and "group by" not in sql.lower():
            assert "limit" in sql.lower(), f"панель-лента {title!r} без LIMIT"


def test_apartments_dynamics_uses_time_picker() -> None:
    """mart_listing_dynamics — по load_date через time-picker; district/style — atemporal (I-15)."""
    sqls = {title: sql for title, sql in _iter_sql(_load("apartments.json"))}
    dyn = next(s for t, s in sqls.items() if "mart_listing_dynamics" in s)
    assert "$__timeFrom()" in dyn and "load_date" in dyn
    # витрины district/style — без time-макросов (atemporal)
    for t, s in sqls.items():
        if "mart_price_area_by_district" in s or "mart_style_renovation_furniture" in s:
            assert "$__time" not in s, f"atemporal-панель {t!r} не должна использовать time-picker"


def test_district_template_variable_present() -> None:
    d = _load("apartments.json")
    names = {v["name"] for v in d["templating"]["list"]}
    assert "district" in names and "DS_TRINO" in names
