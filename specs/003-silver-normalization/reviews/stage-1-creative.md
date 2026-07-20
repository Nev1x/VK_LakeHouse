# Stage 1 — Creative Team, отчёт (003-silver-normalization)

Дата: 2026-07-20. Состав (сжатый, делегированный режим): Creative Analyst + System Analyst.

## Ключевые решения
1. Конфиги: TOML+tomllib (System Analyst; YAML-вариант Creative Analyst отклонён — новая
   зависимость без выигрыша, tomllib stdlib, комментарии поддерживаются). Закрытый набор
   примитивов без eval (оба сошлись).
2. Запись: MERGE INTO (source, external_id), last-write-wins по _ingested_at (Creative) с
   явной I-2-трактовкой точечного upsert; bulk — только явный --reprocess.
3. Типы: DECIMAL(12,2)/DECIMAL(8,2) для денег/площади (System Analyst — точность агрегатов
   004), BIGINT для целых (конвенция 002).
4. Инкрементальность: anti-join bronze._content_hash × журнал stage='transform' (оба);
   watermark отклонён (хрупок при replay).
5. Reprocess: НЕ авто при смене конфига — стоп с подсказкой + явный --reprocess <источник>
   (синтез позиций: авто-детект mismatch от System Analyst + explicit-флаг от Creative).
6. Рефакторинги переиспользования (System Analyst): ident.py, chunked_insert.py (третья копия
   чанк-логики недопустима), runlog.last_status(stage) — багоопасность без фильтра стадии.
7. CUT (Hard Critic-часть): eval-DSL, SCD-история, геокодинг (I-1!), fuzzy cross-source дедуп,
   config-UI, сложное партиционирование (только PARTITIONED BY source).

## Риски (14) — отражены в FR/Edge Cases
Ключевые: источник без конфига (FR-010), конфиг vs реальная bronze-схема (fail fast),
запятая-десятичная из 002 (FR-004), гонки transform/ingest (единый lock FR-012), гранулярность
journal-трекинга = content_hash (FR-011), нестабильный синтетический id (документированная
деградация FR-005).
