"""Конфигурация ingestion из окружения (креды/лимиты) — контракты 001 + FR-014 (002).

Все значения из env (I-7): креды не хардкодятся. Лимиты защиты конфигурируемы (FR-002/NFR-001).
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class IngestConfig:
    minio_endpoint_url: str
    minio_access_key: str
    minio_secret_key: str
    raw_bucket: str
    max_file_bytes: int          # NFR-001 / FR-002: cap размера входного файла
    max_field_bytes: int         # FR-002: cap длины одного поля (utf-8 байт); превышение -> reject
    read_chunk_rows: int         # потоковое чтение (pandas chunksize)
    insert_chunk_rows: int       # строк в одном multi-row INSERT
    insert_chunk_bytes: int      # бюджет ДЛИНЫ ТЕКСТА INSERT (символы; trino инлайнит params)
    lock_path: Path              # файловый lock процесса ingest (FR-011)

    @staticmethod
    def from_env() -> IngestConfig:
        # trino инлайнит bind-параметры в текст запроса; query.max-length=1_000_000 символов.
        # insert_chunk_bytes = бюджет длины ТЕКСТА запроса с запасом (~700k < 1M).
        # max_field_bytes < бюджета, чтобы одно поле никогда не превысило лимит запроса в одиночку.
        return IngestConfig(
            minio_endpoint_url=os.environ.get("MINIO_ENDPOINT_URL", "http://127.0.0.1:9000"),
            minio_access_key=_require("MINIO_ROOT_USER"),
            minio_secret_key=_require("MINIO_ROOT_PASSWORD"),
            raw_bucket=os.environ.get("LOFTNAV_RAW_BUCKET", "raw"),
            max_file_bytes=_int_env("LOFTNAV_MAX_FILE_MB", 500) * 1024 * 1024,
            max_field_bytes=_int_env("LOFTNAV_MAX_FIELD_BYTES", 200_000),
            read_chunk_rows=_int_env("LOFTNAV_READ_CHUNK_ROWS", 5000),
            insert_chunk_rows=_int_env("LOFTNAV_INSERT_CHUNK_ROWS", 1000),
            insert_chunk_bytes=_int_env("LOFTNAV_INSERT_CHUNK_BYTES", 700_000),
            lock_path=pipeline_lock_path(),
        )


def pipeline_lock_path() -> Path:
    """ЕДИНЫЙ lock-файл конвейера: ingest и transform не идут параллельно (FR-012, I-15)."""
    return Path(tempfile.gettempdir()) / "loftnav-pipeline.lock"


# Sanity-диапазоны нормализации silver (FR-004). Обоснование дефолтов — реалии рынка квартир РФ:
# цена > 0 (0/отриц. — ошибка источника); площадь 1..1000 м² (студия..особняк); комнаты 0..20
# (0 = студия); этаж/этажность 1..200 (небоскрёбы); метро 0..240 мин. Переопределяемы через env.
SANITY_DEFAULTS: dict[str, tuple[float, float]] = {
    "price_rub": (0.0, 10_000_000_000.0),   # (эксклюзивный низ проверяется как > 0)
    "area_m2": (1.0, 1000.0),
    "rooms": (0.0, 20.0),
    "floor": (1.0, 200.0),
    "floors_total": (1.0, 200.0),
    "metro_minutes": (0.0, 240.0),
}


@dataclass(frozen=True)
class TransformConfig:
    mapping_dir: Path
    read_chunk_rows: int          # fetchmany bronze (T5)
    merge_chunk_rows: int
    merge_chunk_bytes: int        # бюджет длины текста MERGE (символы)
    regex_value_cap: int          # cap длины значения до regex (ReDoS defense-in-depth, T4)
    regex_timeout_sec: float      # cap ВРЕМЕНИ regex-примитива (SIGALRM watchdog, CRITICAL-1)
    lock_path: Path

    @staticmethod
    def from_env() -> TransformConfig:
        return TransformConfig(
            mapping_dir=Path(os.environ.get("LOFTNAV_MAPPING_DIR", "configs/mapping")),
            read_chunk_rows=_int_env("LOFTNAV_TRANSFORM_READ_CHUNK_ROWS", 5000),
            merge_chunk_rows=_int_env("LOFTNAV_MERGE_CHUNK_ROWS", 1000),
            merge_chunk_bytes=_int_env("LOFTNAV_MERGE_CHUNK_BYTES", 700_000),
            regex_value_cap=_int_env("LOFTNAV_REGEX_VALUE_CAP", 64 * 1024),
            regex_timeout_sec=_float_env("LOFTNAV_REGEX_TIMEOUT_SEC", 2.0),
            lock_path=pipeline_lock_path(),
        )


@dataclass(frozen=True)
class GoldConfig:
    small_sample: int             # порог is_small_sample витрины стиля/ремонта (FR-003)
    lock_path: Path

    @staticmethod
    def from_env() -> GoldConfig:
        return GoldConfig(
            small_sample=_int_env("LOFTNAV_GOLD_SMALL_SAMPLE", 3),
            lock_path=pipeline_lock_path(),
        )


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"Переменная окружения {name} не задана. Скопируй .env.example -> .env и заполни."
        )
    return value
