"""Реестр ридеров: диспетчер по can_read (новый формат = добавить класс в _READERS)."""

from __future__ import annotations

from pathlib import Path

from loftnav.config import IngestConfig
from loftnav.ingest.readers.base import Reader, Source
from loftnav.ingest.readers.csv_reader import CsvReader
from loftnav.ingest.readers.excel_reader import ExcelReader
from loftnav.ingest.readers.json_reader import JsonReader

_READERS = (CsvReader, ExcelReader, JsonReader)

SUPPORTED_SUFFIXES = frozenset({".csv", ".xlsx", ".json", ".jsonl", ".ndjson"})

__all__ = ["SUPPORTED_SUFFIXES", "Reader", "Source", "get_reader"]


def get_reader(path: Path, cfg: IngestConfig) -> Reader:
    for cls in _READERS:
        if cls.can_read(path):
            return cls(cfg)
    raise ValueError(f"неподдерживаемый формат файла: {path.suffix or '(без расширения)'}")
