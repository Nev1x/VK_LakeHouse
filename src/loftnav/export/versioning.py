"""Immutable-версионирование датасета (FR-005): следующий vNNN = max(vNNN)+1 из CommonPrefixes.

Строгий regex ^v\\d{3}$; пустой bucket → v001; мусор не по шаблону — лог+игнор. Коллизия vNNN —
fail-loud на записи (put_or_fail/upload_or_fail), не idempotent-skip.
"""

from __future__ import annotations

import re
import sys

DATASETS_PREFIX = "datasets/"
_VERSION_RE = re.compile(r"^v(\d{3})$")


def next_version(store, prefix: str = DATASETS_PREFIX) -> str:
    """Определяет следующий vNNN по подпрефиксам bucket (полный скан через store.list_prefixes)."""
    max_n = 0
    for full in store.list_prefixes(prefix):
        name = full.rstrip("/").rsplit("/", 1)[-1]
        m = _VERSION_RE.match(name)
        if m:
            max_n = max(max_n, int(m.group(1)))
        else:
            print(f"export: игнорирую не-версионный префикс {full!r}", file=sys.stderr)
    return f"v{max_n + 1:03d}"
