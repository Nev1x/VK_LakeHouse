"""Общая обвязка smoke-тестов: загрузка .env, файловый lock, retry первого запроса.

Smoke гоняется на host против поднятого стека. `.env` подхватывается тут, чтобы
`pytest -q` из корня работал без обязательного `make` (креды в окружении, I-7).
"""

from __future__ import annotations

import os
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LOCK_PATH = Path(tempfile.gettempdir()) / "loftnav-smoke.lock"


def _load_dotenv() -> None:
    """Подгружает ./.env в окружение (не перетирая уже заданные переменные)."""
    env_file = _REPO_ROOT / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv()


@pytest.fixture(scope="session", autouse=True)
def smoke_lock() -> Iterator[None]:
    """Сериализует параллельные smoke-прогоны через O_CREAT|O_EXCL (BSD/macOS-safe, T8).

    Не flock (переносимость make на macOS); битый lock от упавшего прогона снимается по таймауту.
    """
    deadline = time.monotonic() + 60
    fd = None
    while fd is None:
        try:
            fd = os.open(_LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            # осиротевший lock (упавший прогон) старше 5 минут — забираем
            try:
                age = time.time() - _LOCK_PATH.stat().st_mtime
                if age > 300:
                    _LOCK_PATH.unlink(missing_ok=True)
                    continue
            except FileNotFoundError:
                continue
            if time.monotonic() > deadline:
                raise RuntimeError(
                    f"smoke уже выполняется (lock {_LOCK_PATH}); либо снимите lock вручную"
                ) from None
            time.sleep(1)
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield
    finally:
        _LOCK_PATH.unlink(missing_ok=True)


@pytest.fixture
def retry():
    """Фикстура-ретрай с бэкоффом (ленивый каталог: healthy != прогретый, T8/риск 8)."""

    def _retry(fn, *, attempts: int = 15, backoff: float = 3.0, timeout: float = 45.0):
        deadline = time.monotonic() + timeout
        last: Exception | None = None
        for _ in range(attempts):
            try:
                return fn()
            except Exception as exc:  # noqa: BLE001 — smoke-ретрай любой транзиентной ошибки
                last = exc
                if time.monotonic() > deadline:
                    break
                time.sleep(backoff)
        raise AssertionError(f"операция не удалась после ретраев ({timeout:.0f}s): {last}")

    return _retry
