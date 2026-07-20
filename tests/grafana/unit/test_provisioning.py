"""Юнит-тесты provisioning grafana (FR-001/FR-006): структура datasource + secret-check (T8).

Secret-скан хука не ловит generic-пароль — эти тесты первичны: password/secureJsonData обязаны быть
env-ссылками (`$...`), не plaintext.
"""

from __future__ import annotations

from pathlib import Path

import yaml

# parents: [0]=unit, [1]=grafana, [2]=tests, [3]=repo root
_PROV = Path(__file__).resolve().parents[3] / "infra" / "grafana" / "provisioning"
DATASOURCES = _PROV / "datasources"
DASHBOARDS = _PROV / "dashboards"


def _load_yaml(path):
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def test_datasource_structure() -> None:
    data = _load_yaml(DATASOURCES / "trino.yaml")
    ds = data["datasources"][0]
    assert ds["type"] == "trino-datasource"
    assert ds["url"] == "https://trino:8443"        # internal DNS app_net, self-signed
    assert ds["access"] == "proxy"
    assert ds["jsonData"]["tlsSkipVerify"] is True   # self-signed 001
    assert ds["editable"] is False
    assert ds["basicAuth"] is True


def test_datasource_secrets_are_env_refs() -> None:
    """PRIMARY: user/пароль — ТОЛЬКО env-подстановка `${VAR}`, НИКОГДА plaintext (FR-006/I-7)."""
    ds = _load_yaml(DATASOURCES / "trino.yaml")["datasources"][0]
    assert str(ds["basicAuthUser"]).startswith("$"), "user должен быть env-ссылкой"
    password = ds["secureJsonData"]["basicAuthPassword"]
    assert str(password).startswith("$"), "пароль должен быть env-ссылкой, не plaintext"
    # никаких очевидных plaintext-паролей нигде в файле
    raw = (DATASOURCES / "trino.yaml").read_text(encoding="utf-8")
    assert "changeme" not in raw.lower()
    for line in raw.splitlines():
        low = line.lower()
        if "password" in low:
            assert "$" in line, f"строка с password без env-ссылки: {line!r}"


def test_dashboard_provider_valid() -> None:
    prov = _load_yaml(DASHBOARDS / "dashboards.yaml")
    p = prov["providers"][0]
    assert p["type"] == "file"
    assert p["options"]["path"] == "/etc/grafana/provisioning/dashboards"
    assert p["allowUiUpdates"] is False
