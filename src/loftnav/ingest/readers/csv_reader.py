"""CSV-ридер: автодетект разделителя (,/;/tab) и кодировки (utf-8/utf-8-sig/cp1251); chunked."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pandas as pd

from loftnav.config import IngestConfig
from loftnav.ingest.readers.base import Source, normalize_cell

_ENCODINGS = ("utf-8-sig", "utf-8", "cp1251")
_DELIMS = (",", ";", "\t")

# «текстовые» control-байты, допустимые в CSV
_TEXT_CONTROL = {0x09, 0x0A, 0x0D}


def _looks_binary(sample: bytes) -> bool:
    """Эвристика бинарного файла (NUL или >30% control-байт) — cp1251 декодирует почти всё,
    поэтому по кодировке бинарь не отличить; ловим здесь, чтобы broken.bin → failed, не мусор."""
    if not sample:
        return False
    if b"\x00" in sample:
        return True
    ctrl = sum(1 for b in sample if b < 0x20 and b not in _TEXT_CONTROL)
    return ctrl / len(sample) > 0.30


def _detect_encoding(path: Path) -> str:
    sample = path.read_bytes()[:65536]
    if _looks_binary(sample):
        raise ValueError("файл выглядит бинарным, не текстовым CSV")
    for enc in _ENCODINGS:
        try:
            sample.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    return "utf-8"  # последний шанс — errors обработает pandas ниже


def _detect_delimiter(path: Path, encoding: str) -> str:
    with open(path, encoding=encoding, errors="replace") as fh:
        first = fh.readline()
    counts = {d: first.count(d) for d in _DELIMS}
    best = max(counts, key=lambda d: counts[d])
    return best if counts[best] > 0 else ","


class CsvReader:
    @classmethod
    def can_read(cls, path: Path) -> bool:
        return path.suffix.lower() == ".csv"

    def __init__(self, cfg: IngestConfig) -> None:
        self._chunk = cfg.read_chunk_rows

    def sources(self, path: Path) -> Iterator[Source]:
        encoding = _detect_encoding(path)
        delimiter = _detect_delimiter(path, encoding)

        def gen() -> Iterator[dict[str, str | None]]:
            reader = pd.read_csv(
                path,
                sep=delimiter,
                dtype=str,
                keep_default_na=False,
                na_filter=False,
                encoding=encoding,
                encoding_errors="replace",
                chunksize=self._chunk,
                engine="c",
            )
            for chunk in reader:
                cols = list(chunk.columns)
                for row in chunk.itertuples(index=False, name=None):
                    yield {cols[i]: normalize_cell(row[i]) for i in range(len(cols))}

        yield Source(suffix="", records=gen())
