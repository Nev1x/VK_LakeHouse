# Spec 006 — ml-dataset-export (версионированный экспорт датасета)

Статус: stage-1 draft → аудит stage-2. Scope: feature. Intent: `specs/006-ml-dataset-export/intent.md`.
Финальная фича бэклога.

## Overview

CLI `loftnav export-dataset`: читает `gold.apartments_features` (пин на snapshot, ORDER BY id,
чанками) → пишет parquet + jsonl + manifest.json в отдельный bucket `ml-datasets` под
immutable-версией `datasets/vNNN/`; журнал `stage='export'`. Данные не покидают машину («S3» =
локальный MinIO, I-1). **WHY:** замыкает пайплайн — версионированный воспроизводимый датасет
признаков для будущего обучения ML (лофт/не-лофт); манифест и раскладка — frozen по I-6.

## User Stories

- **US-1 Экспорт.** `loftnav export-dataset` → `datasets/vNNN/` с манифестом + файлами.
  _Приёмка:_ `pandas.read_parquet`/`read_json(lines=True)` открывают файл БЕЗ Trino/платформы;
  число строк = manifest.row_count = COUNT(*) features на snapshot (I-13).
- **US-2 Неизменность.** Взятая версия не меняется задним числом. _Приёмка:_ повтор записи в
  существующий vNNN → явная ошибка CLI (не тихая перезапись); новый экспорт → v(NNN+1); старая
  версия побайтово цела (тест).
- **US-3 Трассируемость.** Манифест несёт source_snapshot_id + run_id. _Приёмка:_ snapshot_id —
  реальный снапшот features; повтор без изменений gold → тот же snapshot_id и идентичное
  содержимое (детерминизм).
- **US-4 Наблюдаемость.** Одна запись `stage='export'` в pipeline_runs. _Приёмка:_ try/finally,
  rows_ok=строк; дашборд «Операции» (005) показывает её без правки кода.
- **US-5 Честность манифеста.** Из манифеста видно: is_loft не размечен (всегда NULL), фото —
  ссылки. _Приёмка:_ `target_populated: false` + `photo_handling: "links"` в манифесте и в DoD
  текстом, не implicit.

## Functional Requirements

- **FR-001 CLI.** Сабкоманда `loftnav export-dataset` в реестре cli.py (паттерн build-gold:
  try/except RuntimeError на занятый lock → читаемая ошибка stderr); флаг `--format`
  (parquet|jsonl|both, default both).
- **FR-002 Чтение features.** `SELECT <явный список колонок> FROM iceberg.gold.
  apartments_features FOR VERSION AS OF <snapshot_id> ORDER BY id` через Trino, чанками
  (`fetchmany`, `LOFTNAV_EXPORT_READ_CHUNK_ROWS` default 5000 — bounded, I-15; не fetchall).
  Snapshot фиксируется на СТАРТЕ экспорта (через `apartments_features$snapshots`,
  snapshots_relation вне ident — паттерн 004).
- **FR-003 Форматы.** parquet (pyarrow — новая зависимость, оправдана DoD «читается
  pandas/pyarrow») + jsonl (stdlib json + ЯВНЫЙ encoder для Decimal→str/число и
  timestamp→ISO, иначе падает на первой строке). `--format` выбирает подмножество; both —
  дефолт (jsonl из уже собранных строк дёшев).
- **FR-004 Запись в ml-datasets (I-4 decision record).** Через расширенный `io/s3.py` (boto3;
  единственный S3-модуль): bucket привязан к ИНСТАНСУ (конструктор принимает явный bucket с
  allowlist `{raw, ml-datasets}` — hard-fail на прочее, defense-in-depth против записи в
  warehouse), +`list_objects(prefix,delimiter)`, +`get_object`, +`put_or_fail` (отдельный
  метод: fail-loud на коллизию — НЕ переиспользовать idempotent-skip `put_if_absent` raw).
  _I-4-трактовка (Constitution Gate PASS):_ I-4 регулирует ДОСТУП К ТАБЛИЦАМ medallion (чтение
  managed parquet/metadata в обход Trino). 006 читает features ТОЛЬКО через Trino (FR-002) —
  read-path полностью compliant. Запись в `ml-datasets` — НЕ доступ к таблице: bucket не в
  Iceberg-каталоге, Trino туда не пишет, это терминальная egress-зона выгрузки, структурно
  симметричная raw (терминальный ingress вне каталога) — оба owned одной фичей, разделение
  buckets установлено ещё в 001. «Красная линия» I-4 (запрет прямой записи parquet) прицельно
  про `warehouse`, не про произвольный bucket. Фиксируется в architecture.md; ратифицируется
  approve. _Не-блокер владельцу:_ рекомендован PATCH устава 1.0.0→1.0.1, уточняющий текст
  «единственное исключение» I-4 на две egress/ingress-зоны вне каталога (Часть III — решение
  владельца; см. plan Known Risks).
- **FR-005 Версионирование immutable.** Следующий vNNN — `list_objects(ml-datasets,
  prefix='datasets/', delimiter='/')` → парсинг `v\d{3}` (строгий regex; мусор не по шаблону
  игнорируется с логом) → max+1 (пустой bucket → v001). Перед записью — guard `object_exists`
  на целевой префикс/манифест; коллизия vNNN → **fail-loud** (НЕ put_if_absent-skip — два
  экспорта с одним номером не «тот же контент»). I-2/I-6: vNNN никогда не перезаписывается.
- **FR-006 Порядок записи (atomicity).** Файлы данных пишутся первыми, `manifest.json` —
  ПОСЛЕДНИМ (манифест = маркер валидности версии); частичный сбой до манифеста оставляет
  версию без манифеста = невалидна (не «полу-версия, притворяющаяся готовой»); документируется.
- **FR-007 Манифест (frozen по I-6).** `manifest.json`: `manifest_schema_version` (=1),
  `dataset_version`, `created_at` (UTC ISO, `datetime.now(UTC)` python-стороны — не Trino),
  `run_id`, `source_table`, `source_snapshot_id`, `gold_columns_version`, `row_count`,
  `formats`, `photo_handling: "links"`, `target_populated: false`, `schema` (колонки+типы из
  DESCRIBE features, + null_count для is_loft), `files` (path/format/sha256/size_bytes),
  `loftnav_export_version`. Валидный JSON. Поле-множество = v1 контракта (I-6 явно называет
  манифест ML-датасета замороженной поверхностью).
- **FR-008 Детерминизм.** Пин snapshot (FR-002) + ORDER BY id → одинаковый снапшот даёт
  одинаковый НАБОР и ПОРЯДОК строк. Критерий воспроизводимости — идентичность СОДЕРЖИМОГО
  (хэш канонизированных данных: jsonl-представление / sha256 отсортированных строк), НЕ
  байт-в-байт parquet (parquet embed'ит writer-метаданные/тайминги — сырой файл может
  отличаться). Тест сравнивает содержимое, не сырые байты parquet.
- **FR-009 Фото — ссылки.** `photo_urls` passthrough (VARCHAR JSON as-is), как в gold. Никакого
  скачивания байт (SSRF-риск: URL из непроверенных данных объявлений может указывать на
  внутренние `data_net`-адреса; + storage/legal). Копии — отдельное решение владельца, не в 006.
- **FR-010 Пустой features.** 0 строк → явный warn + решение (success rows_ok=0 с пустыми
  файлами ИЛИ отказ) — не молчаливая «успешная» пустая версия; выбор фиксируется, не implicit.
- **FR-011 Конкурентность.** Общий pipeline-lock (с ingest/transform/build-gold): export
  сериализуется, гонка за vNNN исключена (I-15).
- **FR-012 Журнал.** Одна запись `stage='export'`: `target_table='datasets/vNNN'`,
  `content_hash`=source_snapshot_id, `rows_ok`=строк, `schema_json`={manifest_schema_version};
  try/finally, честные счётчики.
- **FR-013 Зависимости.** +`pyarrow` (пин точной версией) — единственная новая; jsonl/manifest
  — stdlib; boto3/trino/pandas переиспользуются. `S3Store` расширяется, не дублируется.
- **FR-014 Make/тесты.** `make export-dataset` (ARGS=), `make export-dataset-demo`
  (build-gold-demo → export). `tests/export/`: unit (манифест-сериализация, версионинг max+1 и
  пустой→v001, Decimal/timestamp encoder, детерминизм-сортировка, регекс vNNN) + integration
  (requires_stack): export после build-gold-demo → vNNN в ml-datasets, манифест валиден,
  parquet читается pandas/pyarrow НЕЗАВИСИМО (не через S3Store/Trino — реальный DoD-критерий),
  повтор → v(NNN+1) без перезаписи, детерминизм содержимого на одном snapshot.
- **FR-015 Документация.** architecture.md += Export: раскладка ml-datasets, манифест (frozen),
  I-4-трактовка egress-зоны, детерминизм по содержимому, фото-ссылки/SSRF-обоснование,
  fail-loud immutability, порядок записи.

## Non-Functional Requirements

- **NFR-001 Производительность.** export демо-датасета — ≤30с; потоковое чтение (chunked,
  память ≤1GB на росте, I-15 bounded), не fetchall.
- **NFR-002 Надёжность.** Сбой посреди экспорта → версия без манифеста (невалидна), журнал
  failed + error_message; повтор создаёт следующую валидную версию (старые не тронуты).
- **NFR-003 Наблюдаемость.** 100% экспортов в журнале со snapshot_id; structured-логи run_id;
  манифест + sha256 файлов = independent integrity-проверка (I-13).
- **NFR-004 Безопасность.** Данные не покидают машину (I-1); 0 исходящих HTTP (фото-ссылки не
  качаются); креды MinIO/Trino из env; 0 новых портов.
- **NFR-005 Сопровождаемость.** 1 новая зависимость (pyarrow); S3Store расширен, не дублирован;
  манифест frozen additive-only.

## Authentication & Access

Локальный CLI от владельца; Trino — `loftnav`/`TRINO_PASSWORD` (HTTPS:8443, чтение features);
MinIO ml-datasets — root-креды из env через S3Store (запись версий). Новых поверхностей/портов/
ролей нет. SSO отсутствует (устав v1.0.0).

## Out of Scope

- Обучение/разметка модели, train/test split (под задачу обучения, не платформе).
- Скачивание копий фото (SSRF/storage/legal — отдельное решение владельца).
- DVC/lakeFS/внешний dataset-versioning; таблица-реестр версий (папки = реестр).
- Партиционирование/сжатие parquet под объём; крипто-подпись манифеста (sha256 достаточно для
  локального периметра).
- Внешний S3 (только локальный MinIO — I-1).

## Affected Services

Изменяется: `src/loftnav/` (+`export/` пакет: schema, writer, manifest, versioning, run;
+`ExportConfig` в config.py; правки cli.py, `io/s3.py` +bucket-параметр/list/get),
`pyproject.toml` (+pyarrow, console_script уже есть), `Makefile`, `docs/architecture.md`,
`tests/export/**`. Не затрагивается: compose/infra (bucket ml-datasets уже создаётся 001),
харнес, raw/bronze/silver/gold-код (только чтение features), тесты 001-005 (обязаны остаться
зелёными).

## Edge Cases

Пустой features → FR-010; коллизия vNNN → fail-loud; частичный сбой → версия без манифеста
(невалидна, FR-006); Decimal/timestamp в jsonl → encoder; photo_urls битый JSON → passthrough
as-is (не парсим); конкурентный export → lock; мусорная папка не по vNNN-шаблону в bucket →
строгий regex игнорирует с логом; большой датасет → chunked не OOM; parquet байт-в-байт
различается при одном содержимом → тест по содержимому не байтам.

## Assumptions

- Стек и gold 004 живы (`make build-gold-demo` прогнан, apartments_features непуста).
- pyarrow совместим с Python 3.12/pandas 3.0.3 — пин на реализации; parquet читается независимо.
- Bucket ml-datasets существует (bootstrap 001 подтверждён system-analyst).

## Success Criteria

1. `make export-dataset-demo`: `datasets/v001/` в ml-datasets с manifest.json + data.parquet +
   data.jsonl; parquet открывается `pandas.read_parquet` независимо; row_count сходится.
2. Повторный export → v002; v001 побайтово цела; попытка перезаписать v001 → явная ошибка.
3. Манифест: source_snapshot_id реальный, sha256 файлов совпадает с фактическими,
   target_populated=false, photo_handling=links.
4. Детерминизм: два экспорта на одном snapshot → идентичное содержимое (хэш канонизированных
   данных).
5. Журнал `stage='export'` с snapshot_id и rows_ok; видно в дашборде «Операции» (005).
6. `pytest -q && ruff check .` зелёные (001-006); smoke зелёный; secret-скан зелёный; данные не
   покинули машину (0 исходящих HTTP).
