"""Обвязка тестов ingestion: загрузка .env, путь к фикстурам, фабрика конфига, маркер стека."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from loftnav.config import IngestConfig

_REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = _REPO_ROOT / "tests" / "fixtures" / "ingestion"


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


def _build_config(**overrides) -> IngestConfig:
    """IngestConfig с дефолтами и dummy-кредами (для юнит-тестов ридеров без стека)."""
    base = dict(
        minio_endpoint_url="http://127.0.0.1:9000",
        minio_access_key="dummy",
        minio_secret_key="dummy",
        raw_bucket="raw",
        max_file_bytes=500 * 1024 * 1024,
        max_field_bytes=200_000,
        read_chunk_rows=5000,
        insert_chunk_rows=1000,
        insert_chunk_bytes=700_000,
        lock_path=Path(os.environ.get("TMPDIR", "/tmp")) / "loftnav-ingest-test.lock",
    )
    base.update(overrides)
    return IngestConfig(**base)


@pytest.fixture
def make_config():
    """Фабрика IngestConfig (без импорта из conftest — фикстура; см. паттерн smoke)."""
    return _build_config


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "requires_stack: тест требует поднятого стека 001")
