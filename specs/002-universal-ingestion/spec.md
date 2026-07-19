# Spec 002 — universal-ingestion (универсальный загрузчик)

Статус: stage-1 draft → аудит stage-2. Scope: feature. Intent: `specs/002-universal-ingestion/intent.md`.

## Overview

CLI `loftnav ingest <файл|папка>`: приём файлов о квартирах в форматах CSV/XLSX/JSON/JSONL с
заранее неизвестными схемами → immutable raw-копия в MinIO → типизированный append в
`iceberg.bronze.<источник>` через Trino → невалидные строки в quarantine → append-only журнал
прогонов `iceberg.ops.pipeline_runs`. Идемпотентность по контент-хэшу, ошибка одного файла не
роняет батч. **WHY:** первый содержательный слой платформы; журнал и quarantine — frozen-vход
для 003 (silver), 005 (дашборд операций), 006 (экспорт).

## User Stories

- **US-1 Разовая загрузка.** `loftnav ingest file.csv` → raw-копия + bronze-таблица + запись
  журнала. _Приёмка:_ `SELECT count(*)` через Trino = строки файла минус quarantine; raw-объект
  побитово равен исходнику; запись журнала атомарна с завершением (I-3, I-13).
- **US-2 Батч с одним битым файлом.** `loftnav ingest ./incoming/` — остальные файлы загружены,
  битый помечен failed с причиной. _Приёмка:_ exit code = частичный успех (2); запись журнала
  per-файл; ни один валидный файл не пропущен (I-8).
- **US-3 Идемпотентный повтор.** Повторный ingest неизменённого файла не дублирует данные.
  _Приёмка:_ count(*) не растёт; журнал получает запись `skipped` (hash match), не молчание (I-2, I-3).
- **US-4 Изменённый файл с тем же именем.** Новый контент-хэш → обработка как новой версии
  источника; additive-эволюция схемы (новая nullable-колонка). _Приёмка:_ DESCRIBE показывает
  добавленную колонку; старые строки не переписаны; несовместимый тип → quarantine
  «schema conflict», не порча схемы (I-6).
- **US-5 Невалидные строки не теряются.** Валидные → bronze, невалидные →
  `iceberg.quarantine.bronze_<источник>_rejects` с причиной. _Приёмка:_ rows_ok +
  rows_quarantined = строки источника; rejects видны SELECT'ом (I-2, I-9).

## Functional Requirements

- **FR-001 CLI.** Точка входа — console_script `loftnav` (`loftnav.cli:main`), реестр сабкоманд
  (003 добавит `transform`, 006 — `export-dataset` без параллельных entry points).
  `loftnav ingest <path...>` принимает файлы и папки (папка = батч всех поддерживаемых файлов).
- **FR-002 Форматы и ридеры.** Reader-протокол (`ingest/readers/base.py`): CSV (автодетект
  разделителя `,`/`;`/tab; кодировки utf-8/utf-8-sig/cp1251), XLSX (openpyxl
  `load_workbook(read_only=True, data_only=True)` + `iter_rows()` — потоковое чтение БЕЗ
  `pandas.read_excel` (он грузит книгу в память целиком и не умеет chunksize); каждый непустой
  лист = отдельный источник `<источник>_<лист>`; merged cells → значение в левой-верхней,
  остальные NULL), JSON (явная детекция: объект / массив объектов / JSONL). CSV/JSONL — pandas
  `chunksize`. Лимиты защиты (значения конфигурируемы): максимальный размер входного файла
  (default 500 MB), cap длины одного поля/сериализованного JSON (default 1 MB) — превышение →
  quarantine/failed с причиной, не OOM. Новый формат = новый reader-модуль без правки
  диспетчера. `.xls` вне scope.
- **FR-003 Источник и идентификаторы.** Имя bronze-таблицы: `--source <имя>` CLI-флаг; дефолт
  — нормализованный stem файла. ЕДИНАЯ функция санитизации идентификаторов для ВСЕХ имён
  (источник, листы, колонки): whitelist `[a-z0-9_]`, не начинается с цифры, дедупликация,
  замена пустых имён; пользовательские колонки с префиксом `_` переименовываются (`u_...`) —
  служебный `_`-префикс зарезервирован (FR-006). НИ ОДИН идентификатор не попадает в текст
  SQL, минуя эту функцию (I-7); юнит-тест на вредоносные имена (`x"; DROP TABLE--`). Два файла
  с одним источником = осознанное слияние в одну таблицу (различаются `_content_hash`).
- **FR-004 Schema inference.** Только примитивы Iceberg: VARCHAR/BIGINT/DOUBLE/BOOLEAN/DATE/
  TIMESTAMP. Вложенные JSON-структуры (глубина >1) сериализуются в VARCHAR(JSON). Числовая
  локаль: точка — число; запятая-десятичная (`1234,56`) остаётся VARCHAR (без магии;
  нормализация — работа 003). Выведенная схема пишется в журнал (`schema_json`).
- **FR-005 Raw immutable.** Content-addressed ключ `raw/<sha256-hex>/<санитизированное имя
  файла>` (безопасный чарсет; `/`, `..`, control-байты вычищаются; исходное имя as-is живёт в
  журнале `source_file`) через io-адаптер `loftnav/io/s3.py` (boto3; единственный модуль,
  знающий S3 API — I-4). Повторный PUT идентичных байт идемпотентен; перезапись другим
  содержимым по тому же ключу невозможна by construction (хэш в ключе).
- **FR-006 Bronze-запись (I-7: только параметризованный SQL).** `iceberg.bronze.<источник>` +
  служебные колонки `_run_id`, `_content_hash`, `_source_file`, `_ingested_at` (`_`-префикс
  зарезервирован — FR-003). Только через Trino batched INSERT чанками; ЗНАЧЕНИЯ строк — только
  bind-параметрами trino-клиента (`cursor.execute(sql, params)`), ручная сборка VALUES-текста
  из значений ЗАПРЕЩЕНА; идентификаторы в SQL — только из санитайзера FR-003 (то же для ALTER/
  DELETE). Чанк ограничен и строками (≤1000), и байтами (динамическое уменьшение при широких
  строках). DDL bronze-таблиц: `format-version='2'` (row-level DELETE для FR-010), VARCHAR без
  длины (unbounded). Прямая запись parquet в warehouse ЗАПРЕЩЕНА — I-4, красная линия.
- **FR-007 Эволюция схемы.** Строго additive: `ALTER TABLE ADD COLUMN` (nullable). Разрешённые
  promotions: INTEGER→BIGINT, BIGINT→DOUBLE, REAL→DOUBLE. Любой другой конфликт типов → файл в
  quarantine со статусом `failed`, причина «schema conflict» (I-6, никакого auto-widening).
- **FR-008 Quarantine.** Общий модуль `loftnav/quarantine.py` (переиспользует 003):
  `iceberg.quarantine.bronze_<источник>_rejects`, схема: `run_id`, `source`, `raw_record`
  (JSON as-is), `reason` (человекочитаемая), `rejected_at`, `layer`. CREATE TABLE IF NOT
  EXISTS + INSERT; построчная валидация: валидные грузятся, невалидные — сюда.
- **FR-009 Журнал прогонов (frozen, I-3/I-6).** `iceberg.ops.pipeline_runs` — общий для
  002/003/006 (колонка `stage`): `run_id`, `stage`, `started_at`, `finished_at`,
  `source_file`, `content_hash`, `target_table`, `rows_ok`, `rows_quarantined`, `schema_json`,
  `status` (success/partial/failed/skipped), `error_message`. Namespace `ops` добавляется в
  bootstrap. Запись — ОДИН INSERT в конце прогона файла (try/finally; никаких UPDATE —
  append-only). Общий модуль `loftnav/runlog.py`.
- **FR-010 Идемпотентность.** Перед обработкой — SELECT по `content_hash`: `success` → skip
  (журнал `skipped`); `failed`/`partial` → replay: `DELETE FROM bronze WHERE _content_hash=?`
  (bind-параметр; только строки этого файла) → повторная вставка. _I-2 compliance note:_
  raw абсолютно immutable и не затрагивается; DELETE применяется ТОЛЬКО к строкам прогона,
  никогда не имевшего статуса `success` (мусор незавершённой попытки, не зафиксированная
  история); Iceberg-снапшоты не expire (time-travel сохраняет и их); quarantine не трогается;
  журнал получает НОВУЮ запись (старая failed-запись не редактируется — I-3). Механизм
  ратифицируется владельцем утверждением этой спеки (гейт stage-2) и фиксируется фразой в
  architecture.md (FR-016).
- **FR-011 Конкурентность (I-15).** Файловый lock (`os.open(O_CREAT|O_EXCL)`, паттерн smoke)
  на весь процесс ingest; второй параллельный запуск — читаемая ошибка «прогон уже идёт»,
  не гонка.
- **FR-012 Батч-устойчивость (I-8).** Исключение на файле → журнал `failed` + продолжение
  батча. Exit codes: 0 — все успешно/skipped; 1 — все провалились; 2 — частично. Итоговая
  сводка по файлам в stdout.
- **FR-013 Логи (I-9).** Structured key=value с `run_id` на каждом шаге (read → raw → infer →
  bronze → journal); ошибки — с именем файла и причиной.
- **FR-014 Make/env.** `make ingest FILE=<path>`, `make ingest-demo` (грузит
  `tests/fixtures/ingestion/`); `.env.example` += `MINIO_ENDPOINT_URL=http://127.0.0.1:9000`.
- **FR-015 Тесты.** `tests/ingestion/`: юнит (inference, ридеры, нормализация имён, promotions)
  без стека + интеграционные с живым стеком: демо-набор из ≥3 файлов (CSV+XLSX+JSONL, разные
  схемы) через одну команду; идемпотентный повтор; quarantine; битый файл в батче (exit 2).
  Фикстуры — `tests/fixtures/ingestion/` (данные, не .py — pytest/ruff не задевает).
- **FR-016 Документация.** `docs/architecture.md` += раздел Ingestion: контракты журнала,
  quarantine, raw-раскладка, схема bronze-таблиц, CLI/make-команды, exit codes.

## Non-Functional Requirements

- **NFR-001 Производительность.** Демо-набор (3 файла, суммарно ≤10k строк) — ≤60с целиком;
  CSV 100k строк — ≤5 мин; потоковое чтение chunksize ≤5000 строк, INSERT-чанк ≤1000 строк
  (память процесса ≤1GB на гигантском файле — файл не грузится в память целиком).
- **NFR-002 Надёжность.** Частичный сбой файла → журнал `failed` + error_message; replay
  восстанавливает консистентность (FR-010); файл — логическая единица обработки.
- **NFR-003 Наблюдаемость.** 100% прогонов имеют запись журнала; для каждого файла
  rows_ok + rows_quarantined = обработанные строки; журнал SELECT-доступен (вход 005).
- **NFR-004 Безопасность.** Креды Trino/MinIO — только env (контракты 001); данные не покидают
  машину (I-1); 0 новых опубликованных портов.
- **NFR-005 Сопровождаемость.** Новые зависимости запинены точно (pandas, openpyxl, boto3);
  новый формат = 1 новый модуль-ридер.

## Authentication & Access

CLI работает локально от пользователя-владельца. Доступ к Trino — пользователь `loftnav` +
`TRINO_PASSWORD` из env по HTTPS:8443 (self-signed, контракт FR-015 фичи 001); доступ к MinIO —
root-креды из env через `MINIO_ENDPOINT_URL` (127.0.0.1:9000) — осознанный MVP-риск общих
кредов, зафиксирован в 001 (least-privilege — отдельная фича). Новых поверхностей доступа,
портов и ролей фича не добавляет. SSO отсутствует (устав v1.0.0).

## Out of Scope

- Silver-нормализация, маппинг в единую схему квартир (003); агрегаты (004).
- Schema-registry как сервис; streaming/continuous ingestion; оркестрация по расписанию.
- Глубокая структурная типизация JSON (STRUCT/LIST), эвристика «главного листа» Excel.
- Формат `.xls` (legacy binary), Parquet-ридер (расширение через Reader-протокол позже).
- Распределённые локи; least-privilege креды MinIO.
- Дашборды по журналу (005).

## Affected Services

Изменяется: `src/loftnav/` (+`cli.py`, `ingest/` пакет, `quarantine.py`, `runlog.py`,
`config.py`, `io/s3.py`; `bootstrap.py` += namespace `ops`), `pyproject.toml` (+deps,
console_script), `Makefile` (+ingest, ingest-demo), `.env.example` (+MINIO_ENDPOINT_URL),
`docs/architecture.md` (+раздел), `tests/` (+ingestion/, +fixtures/ingestion/).
Не затрагивается: compose-стек 001 (сервисы/порты/сети без изменений), харнес репо,
tests/smoke (должен остаться зелёным), tests/agent-evals.

## Edge Cases

Пустой файл (0 байт) → failed с причиной, батч живёт; файл только с заголовком → success 0/0
(отличим от сбоя); BOM/cp1251 — детект кодировки, кириллица не портится; `;`-CSV; Excel
formulas → значения (`data_only`); merged cells → NULL-ы кроме первой ячейки; JSON
объект-vs-массив-vs-JSONL; дубликаты/пустые имена колонок → нормализация; конфликт типов
внутри файла → колонка VARCHAR при inference, конфликт с существующей схемой → FR-007;
гигантский файл → chunked, не OOM; полностью невалидный файл (бинарник как .csv) → failed,
0/100% quarantine не валит батч; конкурентный запуск → lock-ошибка; обрыв Trino посреди
файла → failed + replay (FR-010).

## Assumptions

- Стек 001 поднят (`make up`); контракты 001 действуют (каталог iceberg, namespace'ы, порты).
- Демо-данные квартир — синтетические фикстуры в репо (реальные файлы владелец принесёт позже).
- pandas/openpyxl/boto3 совместимы с Python 3.12 (пины — на реализации).

## Success Criteria

1. `make ingest-demo`: ≥3 файла разных форматов и схем загружены одной командой; таблицы
   `iceberg.bronze.*` видны и читаются через Trino (I-13).
2. Повторный `make ingest-demo` — счётчики bronze не изменились, журнал получил `skipped`.
3. Битый файл в батче → exit code 2, остальные загружены, журнал `failed` с причиной.
4. Quarantine-строки видны SELECT'ом; rows_ok+rows_quarantined сходится с источником.
5. `SELECT * FROM iceberg.ops.pipeline_runs` показывает все прогоны с run_id/status/schema_json.
6. `pytest -q && ruff check .` зелёные; smoke 001 остаётся зелёным; secret-скан зелёный.
