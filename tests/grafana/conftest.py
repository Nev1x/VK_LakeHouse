"""Обвязка тестов grafana: загрузка .env, путь к provisioning, маркер стека."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
PROVISIONING = _REPO_ROOT / "infra" / "grafana" / "provisioning"
DATASOURCES = PROVISIONING / "datasources"
DASHBOARDS = PROVISIONING / "dashboards"


def _load_dotenv() -> None:
    env_file = _REPO_ROOT / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


@pytest.fixture
def provisioning() -> Path:
    return PROVISIONING


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "requires_stack: тест требует поднятого стека 001")
