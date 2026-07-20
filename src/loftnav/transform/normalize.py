"""Примитивы нормализации значений (FR-004). Декларативные операции, без eval/exec (I-7/I-14).

Деньги/площадь — точная арифметика: str → Decimal → quantize (БЕЗ промежуточного float, аудит #17).
Regex-примитивы с cap длины значения (ReDoS defense-in-depth, T4).
"""

from __future__ import annotations

import datetime as _dt
import re
import signal
from contextlib import contextmanager
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

_CENTS = Decimal("0.01")

# Известные конверсии единиц (FR-004). Расширяется code-review, не eval (NFR-005).
UNIT_FACTORS: dict[tuple[str, str], Decimal] = {
    ("rub", "rub"): Decimal(1),
    ("thousands_rub", "rub"): Decimal(1000),
    ("mln_rub", "rub"): Decimal(1_000_000),
    ("m2", "m2"): Decimal(1),
    ("sotka", "m2"): Decimal(100),
}

_BOOL_TRUE = {"true", "t", "yes", "1", "да"}
_BOOL_FALSE = {"false", "f", "no", "0", "нет"}


class NormalizationError(ValueError):
    """Значение не прошло нормализацию → строка в quarantine с этой причиной."""


class RegexTimeout(NormalizationError):
    """Regex не уложился в отведённое ВРЕМЯ (catastrophic backtracking) → строка в quarantine."""


def casefold_trim(s: str) -> str:
    return s.strip().casefold()


@contextmanager
def _time_limit(seconds: float):
    """Watchdog ВРЕМЕНИ через SIGALRM (CRITICAL-1): cap длины НЕ ограничивает время regex.

    CPython `re` проверяет сигналы во время matching (проверено эмпирически) — setitimer перебивает
    зависший паттерн. Только main-thread (CLI single-threaded); прежний хендлер восстанавливается.
    """
    if seconds <= 0:
        yield
        return

    def _handler(signum, frame):
        raise RegexTimeout(
            f"regex не уложился в {seconds}s — возможен catastrophic backtracking"
        )

    old = signal.signal(signal.SIGALRM, _handler)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)   # снять таймер
        signal.signal(signal.SIGALRM, old)         # восстановить прежний хендлер


def regex_replace(value: str, pattern: str, replacement: str, cap: int, timeout: float) -> str:
    _guard_len(value, cap)
    with _time_limit(timeout):
        return re.sub(pattern, replacement, value)


def regex_extract(value: str, pattern: str, cap: int, timeout: float) -> str | None:
    _guard_len(value, cap)
    with _time_limit(timeout):
        m = re.search(pattern, value)
    if m is None:
        return None
    return m.group(1) if m.groups() else m.group(0)


def _guard_len(value: str, cap: int) -> None:
    if len(value) > cap:
        raise NormalizationError(f"значение длиннее {cap} символов — regex пропущен (ReDoS-guard)")


def cast_decimal(value: str) -> Decimal:
    try:
        return Decimal(value).quantize(_CENTS, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError) as exc:
        raise NormalizationError(f"не DECIMAL: {value!r}") from exc


def cast_bigint(value: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise NormalizationError(f"не BIGINT: {value!r}") from exc


def cast_boolean(value: str) -> bool:
    low = casefold_trim(value)
    if low in _BOOL_TRUE:
        return True
    if low in _BOOL_FALSE:
        return False
    raise NormalizationError(f"не BOOLEAN: {value!r}")


def cast_timestamp(value: str) -> _dt.datetime:
    try:
        return _dt.datetime.fromisoformat(value)
    except ValueError as exc:
        raise NormalizationError(f"не TIMESTAMP: {value!r}") from exc


def unit_convert(value: Decimal, frm: str, to: str) -> Decimal:
    factor = UNIT_FACTORS.get((frm, to))
    if factor is None:
        raise NormalizationError(f"неизвестная конверсия единиц {frm}->{to}")
    return (value * factor).quantize(_CENTS, rounding=ROUND_HALF_UP)


def sanity_ok(field: str, value: object, ranges: dict[str, tuple[float, float]]) -> bool:
    """Проверка диапазона (FR-004; Decimal-сравнение). price_rub: низ эксклюзивен (>0)."""
    rng = ranges.get(field)
    if rng is None or value is None:
        return True
    lo, hi = Decimal(str(rng[0])), Decimal(str(rng[1]))
    v = Decimal(str(value))
    if field == "price_rub":
        return lo < v <= hi
    return lo <= v <= hi
