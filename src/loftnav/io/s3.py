"""S3 io-адаптер (boto3) — ЕДИНСТВЕННЫЙ модуль, знающий S3 API (I-4).

Бизнес-логика/ридеры не импортируют boto3 напрямую. Креды/endpoint — из config (env, I-7).
bucket — параметр КОНСТРУКТОРА с allowlist {raw, ml-datasets}: hard-fail на прочее (defense-in-depth
против записи в warehouse — 006 FR-004). Один инстанс = один bucket (не per-call).
"""

from __future__ import annotations

import boto3
from botocore.client import Config as _BotoConfig
from botocore.exceptions import ClientError

# Разрешённые зоны вне Iceberg-каталога (raw — ingress 002, ml-datasets — egress 006).
ALLOWED_BUCKETS = frozenset({"raw", "ml-datasets"})


class S3Store:
    """Обёртка над MinIO S3, привязанная к одному bucket из allowlist. path-style (MinIO)."""

    def __init__(self, cfg, bucket: str) -> None:
        if bucket not in ALLOWED_BUCKETS:
            raise ValueError(
                f"bucket {bucket!r} не в allowlist {sorted(ALLOWED_BUCKETS)} — "
                "запись вне raw/ml-datasets запрещена (I-4 defense-in-depth)"
            )
        self._bucket = bucket
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
        """Idempotent put (raw, content-addressed): кладёт если нет, иначе no-op. True=положили.

        НЕ использовать для версий 006 — там нужен fail-loud (put_or_fail).
        """
        if self.object_exists(key):
            return False
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data)
        return True

    def _fail_if_exists(self, key: str) -> None:
        if self.object_exists(key):
            raise RuntimeError(f"объект уже есть: {self._bucket}/{key} — перезапись запрещена")

    def put_or_fail(self, key: str, data: bytes) -> None:
        """Fail-loud put: коллизия ключа → RuntimeError (не idempotent-skip). Immutable 006."""
        self._fail_if_exists(key)
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data)

    def upload_or_fail(self, key: str, filepath: str) -> None:
        """Fail-loud потоковая загрузка файла с диска (bounded RAM — не читаем файл в память).

        Коллизия под общим lock исключает TOCTOU (FR-011); guard object_exists — второй барьер.
        """
        self._fail_if_exists(key)
        self._client.upload_file(filepath, self._bucket, key)

    def get_object(self, key: str) -> bytes:
        return self._client.get_object(Bucket=self._bucket, Key=key)["Body"].read()

    def list_prefixes(self, prefix: str) -> list[str]:
        """Полный список подпрефиксов (CommonPrefixes) под prefix с delimiter='/'.

        Пагинация IsTruncated/ContinuationToken — ПОЛНЫЙ скан (иначе занижение max→коллизия vNNN).
        """
        prefixes: list[str] = []
        token: str | None = None
        while True:
            kwargs = {"Bucket": self._bucket, "Prefix": prefix, "Delimiter": "/"}
            if token:
                kwargs["ContinuationToken"] = token
            resp = self._client.list_objects_v2(**kwargs)
            prefixes.extend(p["Prefix"] for p in resp.get("CommonPrefixes", []))
            if not resp.get("IsTruncated"):
                break
            token = resp.get("NextContinuationToken")
        return prefixes
