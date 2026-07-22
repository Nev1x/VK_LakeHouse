"""Интеграция лофт-маркеров 007: silver→features→export (US-1/US-2/US-3). Маркер requires_stack.

Проверяет сквозняк на живом стеке: маркеры в silver (apartments заполнены, lite wall_material NULL),
features/export несут ровно 26 колонок, манифест gold_columns_version=2, СТАРЫЕ версии датасета
immutable (sha manifest.json не меняется). Требует непустой silver (owner-данные / build-gold-demo).
"""

from __future__ import annotations

import hashlib
import io
import json
import os
from decimal import Decimal

import boto3
import pandas as pd
import pytest
from botocore.client import Config as _Cfg

from loftnav.config import ExportConfig, GoldConfig
from loftnav.export.run import EXIT_OK, run_export
from loftnav.export.schema import FEATURES_COLUMNS
from loftnav.gold.run import run_build_gold
from loftnav.trino_client import get_connection

pytestmark = pytest.mark.requires_stack

_MARKERS = ("ceiling_height_m", "wall_material", "year_built")
_EXPECTED_COLUMNS = 26


def _client():
    return boto3.client(
        "s3", endpoint_url=os.environ["MINIO_ENDPOINT_URL"],
        aws_access_key_id=os.environ["MINIO_ROOT_USER"],
        aws_secret_access_key=os.environ["MINIO_ROOT_PASSWORD"],
        region_name="us-east-1",
        config=_Cfg(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def _q(sql, params=None):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, params) if params is not None else cur.execute(sql)
        return cur.fetchall()
    finally:
        conn.close()


def _versions(c) -> list[str]:
    resp = c.list_objects_v2(Bucket="ml-datasets", Prefix="datasets/", Delimiter="/")
    return sorted(p["Prefix"].split("/")[1] for p in resp.get("CommonPrefixes", []))


def _manifest_sha(c, version: str) -> str:
    key = f"datasets/{version}/manifest.json"
    body = c.get_object(Bucket="ml-datasets", Key=key)["Body"].read()
    return hashlib.sha256(body).hexdigest()


def _last_export_version() -> str:
    return _q(
        "SELECT source_file FROM iceberg.ops.pipeline_runs WHERE stage='export' "
        "AND status='success' ORDER BY started_at DESC LIMIT 1"
    )[0][0]


def test_silver_markers_populated_and_lite_null() -> None:
    """US-1/US-3: apartments — маркеры заполнены (диапазоны), lite — wall_material NULL."""
    sources = {r[0] for r in _q("SELECT DISTINCT source FROM iceberg.silver.apartments_clean")}
    if not sources:
        pytest.skip("silver пуст — запусти reprocess/transform-demo")

    if "apartments" in sources:
        r = _q(
            "SELECT min(ceiling_height_m), max(ceiling_height_m), "
            "min(year_built), max(year_built), "
            "count(*) FILTER (WHERE wall_material IS NOT NULL), count(*) "
            "FROM iceberg.silver.apartments_clean WHERE source='apartments'"
        )[0]
        cmin, cmax, ymin, ymax, wall_filled, total = r
        assert Decimal("1.5") <= cmin and cmax <= Decimal("10.0")   # sanity-диапазон потолков
        assert 1800 <= ymin and ymax <= 2100                        # sanity-диапазон года
        assert wall_filled > 0                                       # материалы стен заполнены
        assert total > 0

    if "apartments_lite" in sources:
        lite = _q(
            "SELECT count(*) FILTER (WHERE wall_material IS NOT NULL), "
            "count(*) FILTER (WHERE ceiling_height_m IS NOT NULL), count(*) "
            "FROM iceberg.silver.apartments_clean WHERE source='apartments_lite'"
        )[0]
        assert lite[0] == 0            # wall_material отсутствует в схеме lite → всегда NULL
        assert lite[1] > 0             # ceiling_height_m у lite при этом заполнен


def test_features_and_export_carry_26_columns_v2_old_immutable() -> None:
    """US-2: features/export = 26 колонок; манифест v2; старые версии immutable."""
    silver_n = _q("SELECT count(*) FROM iceberg.silver.apartments_clean")[0][0]
    if silver_n == 0:
        pytest.skip("silver пуст — запусти reprocess/transform-demo")

    assert run_build_gold("apartments_features", GoldConfig.from_env()) == EXIT_OK
    # features несёт ровно 26 колонок, включая 3 маркера, и столько же строк, сколько silver
    desc = {r[0] for r in _q("DESCRIBE iceberg.gold.apartments_features")}
    assert set(FEATURES_COLUMNS) <= desc
    for m in _MARKERS:
        assert m in desc
    assert _q("SELECT count(*) FROM iceberg.gold.apartments_features")[0][0] == silver_n

    c = _client()
    # baseline immutability: sha manifest.json самой старой версии ДО экспорта
    old_versions = _versions(c)
    assert old_versions, "ожидались существующие версии датасета"
    old_v = old_versions[0]
    old_sha = _manifest_sha(c, old_v)

    assert run_export("both", ExportConfig.from_env()) == EXIT_OK
    new_v = _last_export_version()
    assert new_v not in old_versions            # действительно НОВАЯ версия

    # независимое чтение parquet потребителем → ровно 26 колонок, маркеры на месте
    pq = c.get_object(Bucket="ml-datasets", Key=f"datasets/{new_v}/data.parquet")["Body"].read()
    df = pd.read_parquet(io.BytesIO(pq))
    assert len(df.columns) == _EXPECTED_COLUMNS
    assert list(df.columns) == list(FEATURES_COLUMNS)
    for m in _MARKERS:
        assert m in df.columns

    man = json.loads(
        c.get_object(Bucket="ml-datasets", Key=f"datasets/{new_v}/manifest.json")["Body"].read()
    )
    assert man["gold_columns_version"] == 2
    assert len(man["schema"]) == _EXPECTED_COLUMNS
    schema_names = [col["name"] for col in man["schema"]]
    assert schema_names == list(FEATURES_COLUMNS)

    # СТАРАЯ версия не тронута — sha manifest.json тот же (immutable, NFR-002)
    assert _manifest_sha(c, old_v) == old_sha
