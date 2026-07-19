"""Immutable raw-хранилище: content-addressed ключ raw/<sha256>/<safe-name> (FR-005, I-2)."""

from __future__ import annotations

import re
from pathlib import Path

from loftnav.io.s3 import S3Store

# Безопасный чарсет имени в ключе (control-байты, '/', '..' вычищаются; исходное имя — в журнале).
_UNSAFE_RE = re.compile(r"[^A-Za-z0-9._-]")


def safe_object_name(filename: str) -> str:
    name = _UNSAFE_RE.sub("_", filename.strip())
    name = name.lstrip(".") or "file"       # убираем ведущие точки (в т.ч. '..')
    return name[:200]


def raw_key(content_hash: str, filename: str) -> str:
    return f"raw/{content_hash}/{safe_object_name(filename)}"


def store_raw(store: S3Store, path: Path, content_hash: str) -> tuple[str, bool]:
    """PUT сырого файла по content-addressed ключу. Возвращает (key, stored_now)."""
    key = raw_key(content_hash, path.name)
    stored = store.put_if_absent(key, path.read_bytes())
    return key, stored
