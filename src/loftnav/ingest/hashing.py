"""Контент-хэш файла (sha256) для идемпотентности и content-addressed raw (FR-005/FR-010)."""

from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Потоковый sha256-hex файла (без загрузки целиком в память — NFR-001)."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk_size), b""):
            h.update(block)
    return h.hexdigest()
