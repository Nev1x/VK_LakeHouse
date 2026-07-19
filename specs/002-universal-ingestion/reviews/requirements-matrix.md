# Requirements Matrix — 002-universal-ingestion (stage-4)

Источник: адверсарный QA Verifier (проход 1) + верификация фикс-цикла (проход 2, QA Director
лично). Оценка против текущего текста spec.md.

| ID | Статус | Evidence |
|---|---|---|
| FR-001 | DONE | console_script `loftnav`, cli.py с реестром сабкоманд; `loftnav ingest файл|папка` работает (demo) |
| FR-002 | DONE | CSV (`;`/cp1251/BOM), XLSX read_only iter_rows (2 листа, merged→NULL), JSON/JSONL (nested→VARCHAR); лимиты: файл 500MB, поле 200KB → reject (перекалибровано фикс-циклом); битый бинарь → failed с причиной |
| FR-003 | DONE | Единый sanitize_columns/sanitize_identifier: адверсарно подтверждено (колонка `x"; DROP TABLE...` → безопасное имя; `_content_hash` → `u_content_hash`; пустой → col_N, дубль → _2 — после фикса заголовки читаются сами, без pandas-мэнглинга); apartments не пострадала (5/5) |
| FR-004 | DONE | Примитивы Iceberg; `45,5` → VARCHAR; nested JSON → VARCHAR; schema_json в журнале (len 72–174) |
| FR-005 | DONE | raw/<sha256>/<safe-name> в MinIO; повторный PUT идемпотентен |
| FR-006 | DONE | Multi-row параметризованный INSERT одним execute (spike); значения — только bind (адверсарная ячейка `'); DROP TABLE...` легла литералом); чанк по оценке длины инлайнового SQL ≤700K симв.; DDL format_version=2; VARCHAR unbounded |
| FR-007 | DONE | ALTER ADD COLUMN additive; промоции узким списком; schema conflict → failed |
| FR-008 | DONE | quarantine.write_rejects чанково; rejects читаются SELECT; после фикса — сбой quarantine-вставки не теряет строки молча; обрезка raw_record — валидный JSON (_truncated/_original_bytes/_prefix) |
| FR-009 | DONE | iceberg.ops.pipeline_runs (fv2), OPS_NAMESPACES отдельно; ОДИН INSERT в finally; grep UPDATE по src = 0 (кроме hashlib) |
| FR-010 | DONE | success/skipped → skip (баг задвоения после skipped найден и закрыт ещё в первом цикле); replay: DELETE by hash (bind) + reinsert — интеграционный тест «ровно 3, без задвоения» |
| FR-011 | DONE | Конкурентный запуск: второй процесс — читаемая lock-ошибка, 3000 строк без дублей (адверсарно) |
| FR-012 | DONE | exit 0/1/2; сводка по файлам; битый файл не валит батч (demo exit 2) |
| FR-013 | DONE | structured key=value логи с run_id |
| FR-014 | DONE | make ingest FILE / ingest-demo; MINIO_ENDPOINT_URL в .env.example |
| FR-015 | DONE | 44 passed: 33 unit (вкл. инъекции, dup-header, oversized-field) + 7 integration (идемпотентность, replay, quarantine-баланс, large-rows) + 4 smoke |
| FR-016 | DONE | architecture.md += раздел Ingestion (контракты, replay/I-2-трактовка, лимиты, PII-note, exit codes) |
| NFR-001 | DONE | demo 13с (≤60с); 1000×1.2KB → success без QUERY_TEXT_TOO_LARGE; потоковое чтение |
| NFR-002 | DONE | Сбой посреди файла → журнал с ФАКТИЧЕСКИМИ счётчиками + error_message (фикс CRITICAL-1); replay восстанавливает |
| NFR-003 | DONE | rows_ok+rows_quarantined сходится (адверсарный сценарий 800KB: 2+1=3=источник; демо: 5/3/6) |
| NFR-004 | DONE | Креды env; 0 новых портов; данные не покидают машину |
| NFR-005 | DONE | Пины pandas 3.0.3 / openpyxl 3.1.5 / boto3 1.43.51 / requests 2.34.2; новый формат = reader-модуль |
| SC-1 | DONE | ingest-demo: 3 формата/схемы → 4 bronze-таблицы, SELECT-подтверждено (5/3/4/2) |
| SC-2 | DONE | Повтор: счётчики стабильны, журнал skipped (провер. QA-агентом ×3 и QA Director ×2) |
| SC-3 | DONE | broken.csv → exit 2, остальные загружены, журнал failed с причиной |
| SC-4 | DONE | rejects SELECT-читаемы; балансы сходятся |
| SC-5 | DONE | pipeline_runs: все прогоны run_id/status/schema_json, stage='ingest' |
| SC-6 | DONE | pytest 44 passed; ruff clean; smoke 001 4 passed; secret-скан 0 хитов |

**Итог: DONE 27 / PARTIAL 0 / MISSING 0** (16 FR + 5 NFR + 6 SC).
