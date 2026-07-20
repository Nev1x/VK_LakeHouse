"""Юнит-тесты версионирования (FR-005): max+1, пустой→v001, строгий regex, мусор игнорируется."""

from __future__ import annotations

from loftnav.export import versioning


class _FakeStore:
    def __init__(self, prefixes: list[str]) -> None:
        self._p = prefixes

    def list_prefixes(self, prefix: str) -> list[str]:
        return self._p


def test_empty_bucket_v001() -> None:
    assert versioning.next_version(_FakeStore([])) == "v001"


def test_max_plus_one() -> None:
    store = _FakeStore(["datasets/v001/", "datasets/v002/", "datasets/v003/"])
    assert versioning.next_version(store) == "v004"


def test_gaps_use_max_not_count() -> None:
    # мёртвый v002 отсутствует — берём max+1, не count+1
    store = _FakeStore(["datasets/v001/", "datasets/v005/"])
    assert versioning.next_version(store) == "v006"


def test_garbage_prefixes_ignored() -> None:
    store = _FakeStore(["datasets/v002/", "datasets/tmp/", "datasets/v2/", "datasets/backup-v9/"])
    assert versioning.next_version(store) == "v003"  # только v002 валиден -> v003
