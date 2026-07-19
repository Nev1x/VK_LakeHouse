# Plan 002 — universal-ingestion

Вход: `spec.md` (после правок по аудиту stage-2). Отчёт аудита: `reviews/stage-2-audit.md`.

## Technical Approach

Python-пакет `loftnav` расширяется CLI и ingestion-конвейером; данные текут: файл → reader
(потоковый) → schema inference → raw-копия (S3/boto3) → bronze (Trino, параметризованный
INSERT) → quarantine (rejects) → журнал (`iceberg.ops.pipeline_runs`). Ключевые техрешения:

- **T1. Структура кода** [FR-001]: `cli.py` (реестр сабкоманд, console_script `loftnav`),
  пакет `ingest/` (readers/{base,csv_reader,excel_reader,json_reader}, inference, raw_store,
  bronze_writer, hashing, run), общие модули верхнего уровня `quarantine.py`, `runlog.py`,
  `config.py`, `io/s3.py` (boto3 — единственный S3-модуль). Reader = Protocol
  (`detect(path)`, `iter_records(path) -> Iterator[dict]`).
- **T2. Потоковое чтение** [FR-002, NFR-001]: CSV/JSONL — pandas `chunksize=5000`; XLSX —
  openpyxl `read_only=True, data_only=True` + `iter_rows()` (НЕ pandas.read_excel — грузит
  книгу целиком, PERF-1 аудита); JSON-массив — ijson не тянем: файл-массив читается целиком
  только если ≤ лимита размера, иначе failed с причиной (документируется). Лимиты: файл ≤
  `LOFTNAV_MAX_FILE_MB` (default 500), поле ≤ 1 MB → reject строки.
- **T3. Санитизация идентификаторов** [FR-003, I-7]: `sanitize_identifier()` в
  `ingest/inference.py` (или `config.py`): lower, транслит не делаем — не-ASCII → `_`;
  whitelist `[a-z0-9_]`, не начинается с цифры, пустое → `col_N`, дубликаты → суффикс `_2`;
  пользовательский `_`-префикс → `u_`. Все DDL/DML строятся ТОЛЬКО из sanitized-имён,
  двойное квотирование `"name"` в SQL. Юнит-тесты с вредоносными именами.
- **T4. Параметризованные запросы** [FR-006, FR-010, I-7]: значения — только
  `cursor.execute(sql, params)` trino-клиента (поддержку многострочного
  `INSERT ... VALUES (?,...),(?,...)` с плоским списком параметров проверить spike-тестом на
  живом Trino 483 ДО массового кода — COMPAT-2; fallback: execute на чанк со сборкой
  placeholders, но НИКОГДА значений в текст). DELETE — `WHERE _content_hash = ?`.
- **T5. Bronze DDL** [FR-006, FR-007]: `CREATE TABLE IF NOT EXISTS ... WITH
  (format='PARQUET', format_version=2)`; служебные `_run_id/_content_hash/_source_file/
  _ingested_at`; эволюция `ALTER TABLE ADD COLUMN` (nullable), promotions
  INTEGER→BIGINT, BIGINT→DOUBLE, REAL→DOUBLE; иное → файл failed «schema conflict», строки в
  quarantine не идут (файл целиком отклонён). Spike: DELETE по non-partition predicate на
  format-version=2 в Trino 483 (COMPAT-3).
- **T6. Inference** [FR-004]: по первому чанку + уточнение по ходу (просадка типа в пределах
  promotions; конфликт внутри файла → колонка VARCHAR); bool/int/float/date/timestamp/str;
  запятая-десятичная → VARCHAR; вложенные структуры → json.dumps → VARCHAR. `schema_json` — в
  журнал.
- **T7. Журнал** [FR-009]: `runlog.py`: `CREATE SCHEMA IF NOT EXISTS ops` (bootstrap.py — 
  отдельная константа `OPS_NAMESPACES=("ops",)`, НЕ в MEDALLION_NAMESPACES — ARCH-1),
  `CREATE TABLE IF NOT EXISTS iceberg.ops.pipeline_runs (...)` (схема из FR-009,
  format_version=2), один INSERT в конце прогона файла (try/finally). Идемпотентность: SELECT
  последнего статуса по `content_hash` (масштаб журнала — демо-платформа; PERF-4 зафиксирован
  как допущение с ревизией при росте, партиционирование отложено).
- **T8. Quarantine** [FR-008]: `quarantine.py`: `write_rejects(run_id, source, layer, records)`
  → `iceberg.quarantine.bronze_<source>_rejects` (схема FR-008, format_version=2); reason —
  человекочитаемый; cap на raw_record 1 MB.
- **T9. Оркестрация файла** [FR-010, FR-012]: `run.py`: hash → журнальный статус → skip/replay
  → raw PUT → reader/inference → bronze → rejects → журнал; исключение → журнал failed +
  continue батча; exit code агрегируется (0/1/2); лог key=value с run_id (FR-013).
- **T10. Lock** [FR-011]: файловый lock в `${TMPDIR}/loftnav-ingest.lock` через
  `os.open(O_CREAT|O_EXCL)` + pid внутри; stale-lock (нет процесса) — перехват с предупреждением.
- **T11. Make/env/deps** [FR-014]: `make ingest FILE=...`, `make ingest-demo`;
  `.env.example` += `MINIO_ENDPOINT_URL`; pyproject: `pandas`, `openpyxl`, `boto3` точными
  пинами (актуальные на момент реализации), console_script; `requests` доехать в dev-deps
  (использует smoke — пробел 001, чиним попутно с пометкой в learnings).
- **T12. Тесты** [FR-015]: `tests/ingestion/unit/` (inference, sanitizer — вкл. инъекции,
  ридеры на фикстурах, promotions) без стека; `tests/ingestion/integration/` (маркер
  `requires_stack`): demo-набор, идемпотентность, replay после искусственного failed,
  quarantine, битый файл (exit 2), коллизия `_`-колонки. Фикстуры `tests/fixtures/ingestion/`:
  apartments.csv (`;`, cp1251, запятая-десятичная), listings.xlsx (2 листа, merged cell),
  flats.jsonl (вложенный объект), broken.bin (переименован в .csv), плюс edge-мелочи.
- **T13. Документация** [FR-016]: architecture.md += раздел Ingestion (конвейер, контракты
  журнала/quarantine/raw, replay и I-2-трактовка (ARCH-2: DELETE только failed/partial,
  снапшоты сохраняются), exit codes, лимиты, PII-note про quarantine as-is (SEC-5), откат:
  additive-колонки при необходимости дропаются вручную без потери данных).

## Units of Work

- **u1-io-core** — io/s3.py, config.py, sanitizer, hashing, lock [FR-003, FR-005, FR-011, T3, T10]
- **u2-readers-inference** — readers CSV/XLSX/JSON+JSONL, inference, лимиты [FR-002, FR-004, T2, T6]
- **u3-write-path** — bronze_writer (T4/T5), quarantine.py, runlog.py, bootstrap ops [FR-006,
  FR-007, FR-008, FR-009, FR-010]
- **u4-cli-batch** — cli.py, run.py, exit codes, логи, Make/env [FR-001, FR-012, FR-013, FR-014]
- **u5-tests-docs** — тесты и фикстуры, architecture.md [FR-015, FR-016, NFR-001..NFR-005]

## Implementation Steps

1. Spike (T4/T5, COMPAT-2/3): на живом стеке проверить параметризованный multi-row INSERT и
   predicate-DELETE на format-version=2; выбрать и записать стратегию вставки. [FR-006]
2. u1-io-core → юнит-тесты санитайзера/хэша.
3. u2-readers-inference → юнит-тесты на фикстурах (без стека).
4. u3-write-path → интеграционно на живом стеке (bronze/quarantine/journal видны SELECT'ом).
5. u4-cli-batch → `make ingest-demo` end-to-end, exit codes, идемпотентный повтор, replay.
6. u5-tests-docs → полный прогон `pytest -q && ruff check .`, smoke 001 зелёный, замер
   NFR-001 (демо ≤60с), architecture.md.

## Files to Create/Modify

Создаются: `src/loftnav/cli.py`, `src/loftnav/config.py`, `src/loftnav/quarantine.py`,
`src/loftnav/runlog.py`, `src/loftnav/io/{__init__,s3}.py`, `src/loftnav/ingest/…`
(readers/{__init__,base,csv_reader,excel_reader,json_reader}.py, inference.py, raw_store.py,
bronze_writer.py, hashing.py, run.py, __init__.py), `tests/ingestion/**`,
`tests/fixtures/ingestion/**`. Изменяются: `src/loftnav/bootstrap.py` (+OPS_NAMESPACES),
`pyproject.toml` (deps, console_script), `Makefile` (+ingest, ingest-demo), `.env.example`
(+MINIO_ENDPOINT_URL), `docs/architecture.md` (+раздел). Не трогаются: compose/infra 001,
харнес, tests/smoke (кроме зелёного статуса), tests/agent-evals.

## Known Risks

1. **Пропускная способность INSERT VALUES** (PERF-2): NFR-001 (100k ≤5 мин) не подтверждён —
   spike шага 1 + замер в приёмке; small-file problem Iceberg — follow-up кандидат (OPTIMIZE).
2. **executemany trino-клиента** (COMPAT-2) — может оказаться циклом execute; закрывается
   spike, стратегия фиксируется до массового кода.
3. **DELETE на format-version=2** (COMPAT-3) — spike шага 1; при неподдержке — fallback:
   пометка строк умершего прогона... нет, fallback: полное пересоздание таблицы источника
   недопустимо → эскалация в план-ревизию (риск низкий по знаниям о Trino 483).
4. **Рост журнала** (PERF-4) — full-scan по content_hash; принято как допущение демо-масштаба,
   ревизия при >10^5 прогонов (запись в architecture.md).
5. **JSON-массив без стриминга** (T2) — файл-массив > лимита → failed с причиной; JSONL —
   рекомендуемый формат для больших объёмов (документируется).
6. **PII в quarantine as-is** (SEC-5) — осознанный риск локальной single-user платформы,
   фиксируется в architecture.md.

## Traceability

FR-001→T1/u4 · FR-002→T2/u2 · FR-003→T3/u1 · FR-004→T6/u2 · FR-005→T2/u1(raw_store в u3-пути
записи через io/s3 из u1) · FR-006→T4/T5/u3/шаг1 · FR-007→T5/u3 · FR-008→T8/u3 · FR-009→T7/u3 ·
FR-010→T9/u3 · FR-011→T10/u1 · FR-012→T9/u4 · FR-013→T9/u4 · FR-014→T11/u4 · FR-015→T12/u5 ·
FR-016→T13/u5 · NFR-001→T2/шаг6 · NFR-002→T9 · NFR-003→T7/шаг4 · NFR-004→T11 · NFR-005→T1/T11.
