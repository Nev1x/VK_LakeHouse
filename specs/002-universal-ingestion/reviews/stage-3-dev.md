# Stage 3 — Dev, отчёт (002-universal-ingestion)

Дата: 2026-07-20. Исполнитель: kulibin; Tech Lead — основная сессия.

## Результат
Units u1–u5 DONE. CLI `loftnav ingest` работает end-to-end: demo-набор (CSV cp1251/';',
XLSX 2 листа/merged, JSONL nested, битый бинарь) → raw → bronze (4 таблицы) → quarantine →
журнал iceberg.ops.pipeline_runs. Пины: pandas 3.0.3, openpyxl 3.1.5, boto3 1.43.51,
requests 2.34.2 (закрыт пробел 001). Пакет 0.2.0.

## Spike (шаг 1 плана, живой Trino 483)
Multi-row параметризованный INSERT одним execute на чанк — выбран (executemany у trino-клиента
шлёт построчно — отвергнут); DELETE по _content_hash на format_version=2 работает (replay).

## Решения/отклонения
1. Инференс по первому чанку + row-level quarantine для поздних конфликтов (упрощение T6).
2. FR-010: skip при success И skipped — баг задвоения после skipped найден интеграционным
   тестом и закрыт в этом же цикле.
3. Эвристика _looks_binary для битых файлов (cp1251 декодирует любые байты).
4. Один dev-reset синтетики (pipeline_runs + demo-таблицы) после фикса бага — до реальных
   данных; штатная работа журнала append-only.

## Верификация (двойная: kulibin + независимо Tech Lead)
- pytest 40 passed; ruff clean; smoke 001 — 4 passed. ✔ оба
- make ingest-demo: 13с (NFR ≤60с), exit 2 (broken.csv failed с причиной); повтор — skipped,
  счётчики не растут. ✔ оба
- Trino SELECT (Tech Lead): bronze.apartments=5, 4 bronze-таблицы, журнал
  success/skipped/failed/partial. ✔
- Replay без задвоения и quarantine-баланс rows_ok+quarantined=строки источника — 
  интеграционные тесты kulibin. ✔

## Хвосты → stage-4/бэклог
PII в quarantine as-is; full-scan журнала (демо-масштаб); JSON-массив без стриминга (JSONL
для больших); header-only CSV → success 0/0 без таблицы.
