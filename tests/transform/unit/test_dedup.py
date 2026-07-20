"""Юнит-тесты identity и дедупа (FR-005): анти-коллизия id (аудит #15), last-write-wins."""

from __future__ import annotations

import datetime as dt

from loftnav.transform.dedup import dedup_latest, make_id


def test_make_id_collision_resistant() -> None:
    # наивный f"{source}:{external_id}" дал бы одинаковый ключ — length-prefix различает
    assert make_id("a", "b:c") != make_id("a:b", "c")
    assert make_id("s", "e") == make_id("s", "e")   # детерминизм
    assert len(make_id("s", "e")) == 64


def test_dedup_latest_keeps_newest() -> None:
    rows = [
        {"external_id": "e1", "_ingested_at": dt.datetime(2026, 1, 1), "price_rub": 100},
        {"external_id": "e1", "_ingested_at": dt.datetime(2026, 3, 1), "price_rub": 150},
        {"external_id": "e2", "_ingested_at": dt.datetime(2026, 2, 1), "price_rub": 200},
    ]
    out = {r["external_id"]: r for r in dedup_latest(rows)}
    assert len(out) == 2
    assert out["e1"]["price_rub"] == 150   # позднее _ingested_at победило
    assert out["e2"]["price_rub"] == 200
