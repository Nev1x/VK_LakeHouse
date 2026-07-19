"""S3 io-адаптер (boto3) — ЕДИНСТВЕННЫЙ модуль, знающий S3 API (I-4).

Бизнес-логика/ридеры не импортируют boto3 напрямую. Креды/endpoint — из IngestConfig (env, I-7).
"""

from __future__ import annotations

import boto3
from botocore.client import Config as _BotoConfig
from botocore.exceptions import ClientError

from loftnav.config import IngestConfig


class S3Store:
    """Обёртка над MinIO S3: idempotent put + exists. path-style (MinIO)."""

    def __init__(self, cfg: IngestConfig) -> None:
        self._bucket = cfg.raw_bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=cfg.minio_endpoint_url,
            aws_access_key_id=cfg.minio_access_key,
            aws_secret_access_key=cfg.minio_secret_key,
            region_name="us-east-1",
            config=_BotoConfig(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    def object_exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return False
            raise

    def put_if_absent(self, key: str, data: bytes) -> bool:
        """Кладёт объект, если его ещё нет. Возвращает True если положили, False если уже был.

        Content-addressed ключ (хэш в пути): одинаковые байты => один ключ => идемпотентно (FR-005).
        перезапись другим содержимым по тому же ключу невозможна by construction.
        """
        if self.object_exists(key):
            return False
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data)
        return True
