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
            lock_path=Path(tempfile.gettempdir()) / "loftnav-ingest.lock",
        )


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"Переменная окружения {name} не задана. Скопируй .env.example -> .env и заполни."
        )
    return value
