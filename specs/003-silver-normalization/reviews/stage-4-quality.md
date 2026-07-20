# Stage 4 — Quality, отчёт (003-silver-normalization)

Дата: 2026-07-20. Состав (делегированный режим): адверсарный QA Verifier + QA Director.
Матрица — requirements-matrix.md.

## Проход 1 → FAIL (retry 1)

Адверсарно подтверждено: SQL-инъекции через значения и external_id с ':' отбиты (bind +
length-prefix id); sanity-границы точны; MERGE last-write-wins защищает от отката старой
версией; идемпотентность reprocess; код-ревью чист (bind везде, fetchmany, Decimal без float,
tomllib rb, 0 TODO, оба call-site last_status со stage). Найдено: **CRITICAL-1** — ReDoS-защита
ограничивала длину значения, но не ВРЕМЯ regex: `(a+)+$` на 30 символах вешал transform >25с,
единый lock блокировал ingest, нужен kill -9. WARN-1: quarantine копил дубли reject при
reprocess (silver чистится, quarantine — нет). INFO-1/2: демо-конфиги в доке, широкий scope
reprocess.

## Fix-цикл (stage-3, kulibin)

SIGALRM-watchdog ограничивает время каждого regex-примитива (эмпирически подтверждено, что
CPython 3.12 re реагирует на сигнал во время matching); timeout → строка в quarantine, не
зависание, lock освобождается. reprocess чистит quarantine источника симметрично silver DELETE
и сужен до одного --source. Документация согласована. +4 теста. Checkpoint: fix-коммит.

## Проход 2 → верификация (QA Director лично)

pytest 78 passed; ruff clean; smoke 4 passed; ReDoS-timeout тесты (3) проходят за ~1с (suite
не виснет); live-transform с патологическим конфигом завершается exit 0 (не 124/зависание);
diff — только файлы реализации 003. Адверсарные оси прохода 1, не затронутые фиксом (инъекции,
sanity, last-write-wins, код-ревью), остаются валидным evidence.

## Вердикт: **PASS** (retry 1 из 2)

Основание: матрица 27/27 DONE; CRITICAL 0 после фикс-цикла; тесты/линт/смок зелёные; ReDoS
закрыт по времени; инъекции отбиты адверсарно; рефакторинги переиспользования не сломали 002.

## Хвосты → бэклог

Cross-source дедуп (Out of Scope); PERF-4 (full-scan журнала) расширен на transform;
merge-on-read компакция (OPTIMIZE) вне MVP; PII в quarantine as-is; синтетический external_id
best-effort. Все документированы в architecture.md.
