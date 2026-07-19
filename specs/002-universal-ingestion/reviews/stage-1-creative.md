# Stage 1 — Creative Team, отчёт (002-universal-ingestion)

Дата: 2026-07-20. Состав (сжатый, делегированный режим): Creative Analyst (объединённая роль
Brainstormer+Critical Analyst+Hard Critic) + System Analyst. Директор — основная сессия.

## Решения, вошедшие в spec.md
1. Движок: pandas+openpyxl, chunked (альтернативы pyarrow/polars/stdlib отклонены: Excel-гэп /
   лишняя зависимость / самопальный inference). pyarrow — запасной путь при проблемах маппинга.
2. Bronze «таблица на источник» (файл-таблица и megatable — CUT); источник = --source флаг,
   дефолт от stem файла; Excel-лист = отдельный источник.
3. Журнал iceberg.ops.pipeline_runs (новый namespace ops, отдельно от medallion) — ОБЩИЙ для
   002/003/006 через stage-колонку; идемпотентность по content_hash в журнале (манифест-файл
   в raw — CUT: не транзакционен, второй источник истины).
4. Raw content-addressed raw/<sha256>/<имя> (дата-префикс отклонён: журнал несёт время).
5. Вставка только через Trino batched INSERT (parquet напрямую — красная линия I-4).
6. Replay-семантика failed-файлов через DELETE по _content_hash (только своя техническая
   очистка bronze; raw/quarantine не трогаются).
7. Лок: файловый O_CREAT|O_EXCL (распределённые локи — CUT, single-machine I-1).
8. CUT/SIMPLIFY по Hard Critic: schema-registry-сервис, streaming, .xls, deep-struct JSON,
   эвристика листов Excel, универсальный type-promotion движок (узкий список promotions).

## Открытые вопросы стадии — закрыты решениями директора
Источник (флаг+дефолт), lock (file-lock), decimal-локаль (запятая → VARCHAR, без магии),
мульти-лист (каждый лист = источник). Зафиксированы в FR-002/003/004/011.

## Риски (18 шт.) — все отражены в Edge Cases/FR спеки
Ключевые: кодировки/BOM/cp1251, разделители, merged cells/формулы, JSON-детекция, OOM на
гигантском файле, конфликт типов, гонки конкурентных прогонов, частичный сбой посреди файла.
