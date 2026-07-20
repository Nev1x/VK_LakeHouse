"""Юнит-тесты границ S3Store (FR-004): bucket-allowlist {raw, ml-datasets}, hard-fail на прочее."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from loftnav.io.s3 import ALLOWED_BUCKETS, S3Store


@dataclass
class _Cfg:
    minio_endpoint_url: str = "http://127.0.0.1:9000"
    minio_access_key: str = "dummy"
    minio_secret_key: str = "dummy"


def test_allowlist_contract() -> None:
    assert ALLOWED_BUCKETS == frozenset({"raw", "ml-datasets"})


@pytest.mark.parametrize("bucket", ["warehouse", "iceberg", "", "ML-DATASETS", "raw/x"])
def test_bad_bucket_hard_fail(bucket) -> None:
    with pytest.raises(ValueError, match="allowlist"):
        S3Store(_Cfg(), bucket)


@pytest.mark.parametrize("bucket", ["raw", "ml-datasets"])
def test_allowed_bucket_constructs(bucket) -> None:
    # конструктор создаёт boto3-клиент (без соединения) — allowlist пройден
    store = S3Store(_Cfg(), bucket)
    assert hasattr(store, "put_or_fail") and hasattr(store, "put_if_absent")
    assert hasattr(store, "upload_or_fail") and hasattr(store, "list_prefixes")
