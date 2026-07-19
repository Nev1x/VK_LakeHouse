# coordination/ — lease-реестр параллельных сессий (spec 017, control plane трек A)

Сессия (worktree-ветка) объявляет занятые пути tracked-файлом `leases/<slug>.lease`.
Enforcement — pre-commit-хук и lease-чек публикации; этот каталог — данные, не код.
Lease-файлы = живые инстанс-данные: синк адаптаций их НЕ читает и НЕ перезаписывает (I-2/I-15).

## Формат lease-файла (key:value; пишет ТОЛЬКО scripts/coordination-lease.sh)

    session: <имя worktree-ветки>              # идентификатор сессии; поля host НЕТ (I-1)
    scope: spec-dir|file|subsystem
    path: <repo-relative путь или bash-глоб>   # по строке на путь; ≤32 строк
    created: 2026-07-06T12:00:00Z              # ISO-8601 UTC (Z)
    ttl_hours: 8                               # целое; created+ttl < now = lease не действует

Лимиты-guard (D-8): файл ≤2048 байт, paths ≤32, пути только repo-relative
(абсолютный путь — отказ, периметр I-1), slug — только `[A-Za-z0-9._-]`.

## Usage

    bash scripts/coordination-lease.sh take <slug> <scope> <ttl_hours> <path>...
    bash scripts/coordination-lease.sh release <slug>
    bash scripts/coordination-lease.sh list

## Честная семантика: best-effort, НЕ распределённый лок

Git не даёт атомарного лока — lease виден другим сессиям только после commit+push и их
fetch. Обязательный первый шаг перед take: fetch + уведомление активных сессий (конвенция —
`docs/pipeline-rules.md`). Просроченный lease не действует: хук пропускает, take перезаписывает.
Take/release идемпотентны (I-15); события lease:take/release — в ops-journal best-effort (I-8).
