"""JSON-ридер: явная детекция объект / массив объектов / JSONL (FR-002).

JSONL — потоково (строка = запись); .json-массив читается целиком только если файл ≤ лимита
размера (стриминг массива вне scope — JSONL рекомендован для больших объёмов).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from loftnav.config import IngestConfig
from loftnav.ingest.readers.base import Source, normalize_cell


class JsonReader:
    @classmethod
    def can_read(cls, path: Path) -> bool:
        return path.suffix.lower() in (".json", ".jsonl", ".ndjson")

    def __init__(self, cfg: IngestConfig) -> None:
        self._max_bytes = cfg.max_file_bytes

    def sources(self, path: Path) -> Iterator[Source]:
        if path.suffix.lower() in (".jsonl", ".ndjson"):
            yield Source(suffix="", records=self._iter_jsonl(path))
            return
        yield Source(suffix="", records=self._iter_json(path))

    def _iter_jsonl(self, path: Path) -> Iterator[dict[str, str | None]]:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                if not isinstance(obj, dict):
                    raise ValueError("JSONL: строка не является объектом")
                yield _flatten(obj)

    def _iter_json(self, path: Path) -> Iterator[dict[str, str | None]]:
        if path.stat().st_size > self._max_bytes:
            raise ValueError("JSON-массив превышает лимит размера — используй JSONL для больших")
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            yield _flatten(data)
        elif isinstance(data, list):
            for obj in data:
                if not isinstance(obj, dict):
                    raise ValueError("JSON-массив содержит не-объект")
                yield _flatten(obj)
        else:
            raise ValueError("JSON: ожидается объект или массив объектов")


def _flatten(obj: dict) -> dict[str, str | None]:
    return {str(k): normalize_cell(v) for k, v in obj.items()}
