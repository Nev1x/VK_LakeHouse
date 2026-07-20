"""Интеграционные тесты export-dataset на живом стеке (FR-005..FR-012). Маркер requires_stack.

Требуют непустой features (make build-gold-demo). Независимое чтение parquet (не через платформу),
immutable-версии, детерминизм содержимого, 0 исходящих HTTP.
"""

from __future__ import annotations

import io
import json
import os
import socket

import boto3
import pandas as pd
import pytest
from botocore.client import Config as _Cfg

from loftnav.config import ExportConfig
from loftnav.export.run import EXIT_OK, run_export
from loftnav.trino_client import get_connection

pytestmark = pytest.mark.requires_stack


def _consumer_client():
    """boto3-клиент как ВНЕШНИЙ потребитель (не через S3Store) — реальный DoD-критерий чтения."""
    return boto3.client(
        "s3", endpoint_url=os.environ["MINIO_ENDPOINT_URL"],
        aws_access_key_id=os.environ["MINIO_ROOT_USER"],
        aws_secret_access_key=os.environ["MINIO_ROOT_PASSWORD"],
        region_name="us-east-1",
        config=_Cfg(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def _last_export_version() -> str:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT source_file FROM iceberg.ops.pipeline_runs WHERE stage='export' "
            "AND status='success' ORDER BY started_at DESC LIMIT 1"
        )
        return cur.fetchall()[0][0]
    finally:
        conn.close()


def _features_count() -> int:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM iceberg.gold.apartments_features")
        return cur.fetchall()[0][0]
    finally:
        conn.close()


def test_export_version_manifest_and_independent_read() -> None:
    """export → vNNN; parquet читается pandas НЕЗАВИСИМО; manifest валиден, sha==факт (крит.1/3)."""
    assert run_export("both", ExportConfig.from_env()) == EXIT_OK
    version = _last_export_version()
    c = _consumer_client()

    def get(name):
        return c.get_object(Bucket="ml-datasets", Key=f"datasets/{version}/{name}")["Body"].read()

    pq_bytes = get("data.parquet")
    df = pd.read_parquet(io.BytesIO(pq_bytes))            # НЕ через S3Store/Trino
    assert len(df) == _features_count()
    man = json.loads(get("manifest.json"))               # валидный JSON
    assert man["row_count"] == len(df)
    assert man["target_populated"] is False and man["photo_handling"] == "links"
    assert man["source_snapshot_id"] is not None
    import hashlib
    actual = hashlib.sha256(pq_bytes).hexdigest()
    pq_meta = next(f for f in man["files"] if f["path"] == "data.parquet")
    assert pq_meta["sha256"] == actual                   # sha манифеста == факт файла


def test_repeat_new_version_immutable_and_deterministic() -> None:
    """Повтор → v(N+1); старая цела; содержимое детерминировано на том же snapshot (крит.2/4)."""
    run_export("both", ExportConfig.from_env())
    v_a = _last_export_version()
    c = _consumer_client()
    a_manifest = json.loads(
        c.get_object(Bucket="ml-datasets", Key=f"datasets/{v_a}/manifest.json")["Body"].read()
    )
    run_export("both", ExportConfig.from_env())
    v_b = _last_export_version()
    assert v_b != v_a                                    # новая версия
    b_manifest = json.loads(
        c.get_object(Bucket="ml-datasets", Key=f"datasets/{v_b}/manifest.json")["Body"].read()
    )
    # детерминизм СОДЕРЖИМОГО (jsonl-sha), не байт parquet; тот же snapshot
    a_jsonl = next(f["sha256"] for f in a_manifest["files"] if f["path"] == "data.jsonl")
    b_jsonl = next(f["sha256"] for f in b_manifest["files"] if f["path"] == "data.jsonl")
    assert a_jsonl == b_jsonl
    assert a_manifest["source_snapshot_id"] == b_manifest["source_snapshot_id"]


def test_zero_external_http(monkeypatch: pytest.MonkeyPatch) -> None:
    """0 исходящих HTTP: во время export НЕТ соединений вне localhost (фото не качаются, крит.6)."""
    allowed = {"127.0.0.1", "::1", "localhost"}
    external: list[str] = []
    real_connect = socket.socket.connect

    def guarded(self, address):
        host = address[0] if isinstance(address, tuple) else str(address)
        if host not in allowed:
            external.append(host)
        return real_connect(self, address)

    monkeypatch.setattr(socket.socket, "connect", guarded)
    assert run_export("both", ExportConfig.from_env()) == EXIT_OK
    assert external == [], f"обнаружены внешние соединения: {external}"
