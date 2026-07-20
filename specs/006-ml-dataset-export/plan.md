# Plan 006 — ml-dataset-export

Вход: `spec.md` (после правки FR-004). Отчёт аудита: `reviews/stage-2-audit.md`.

## Technical Approach

Пакет `src/loftnav/export/` (schema, writer, manifest, versioning, run) поверх общих модулей;
единый read-loop из Trino (snapshot-пин, chunked) с потоковой записью parquet+jsonl; immutable
версии в ml-datasets через расширенный S3Store; журнал stage='export'. Техрешения:

- **T1. pyarrow spike** [C1/C2, FR-013]: установить точную версию pyarrow, подтвердить wheel
  под Python 3.12 + arm64/x86_64; выбрать `pyarrow.parquet.ParquetWriter` (потоковая запись по
  чанкам), НЕ `df.to_parquet()` (пишет целиком). Пин в pyproject.
- **T2. S3Store расширение (границы)** [S1/S5, FR-004]: bucket — параметр КОНСТРУКТОРА с
  allowlist `{raw, ml-datasets}` (hard-fail на прочее — защита от записи в warehouse);
  `list_objects(prefix, delimiter)` (парсинг `CommonPrefixes`, НЕ `Contents`; обработка
  `IsTruncated`/`ContinuationToken` — полный скан, иначе занижение max→коллизия vNNN),
  `get_object`, `put_or_fail` (отдельный метод fail-loud — не путать с idempotent `put_if_absent`).
- **T3. Чтение features** [FR-002, P3/C5]: snapshot-пин через `marts.snapshots_relation(
  'iceberg.gold','apartments_features')` (переиспользовать, не писать заново); `SELECT <явные
  колонки> FROM apartments_features FOR VERSION AS OF <snapshot> ORDER BY id`; `fetchmany(
  LOFTNAV_EXPORT_READ_CHUNK_ROWS=5000)`. null_count is_loft — отдельным агрегатным запросом
  (не итерацией в Python).
- **T4. Потоковая запись (единый проход)** [P1/P2/C2, NFR-001]: ОДИН read-loop fetchmany → на
  каждый чанк: (1) `ParquetWriter.write_table(pa.Table.from_pylist(chunk))`, (2) jsonl-строки в
  файл, (3) инкремент sha256 обоих файлов. Оба writer'а открыты один раз, закрыты в конце.
  Пиковая память ≤ размер чанка, не весь датасет.
- **T5. jsonl encoder** [C3, FR-003]: Decimal→**строка** (сохраняет DECIMAL-точность источника,
  консистентно; float потерял бы точность); timestamp→ISO; в манифесте/architecture.md явно
  зафиксировать, что деньги/площадь в jsonl — строки (типовое расхождение с parquet-decimal
  ожидаемо).
- **T6. Версионирование** [FR-005, A3]: `list_objects` → строгий regex `^v\d{3}$` по
  CommonPrefixes → max+1 (пустой → v001; мусор не по шаблону — лог+игнор); guard object_exists
  на манифест целевой версии → коллизия `put_or_fail` fail-loud. Мёртвая версия без манифеста
  номер не переиспользует (max+1 по префиксам).
- **T7. Порядок записи** [FR-006, A2]: data-файлы первыми, manifest.json ПОСЛЕДНИМ (= маркер
  валидности); частичный сбой → версия без манифеста невалидна. Опциональный
  `export-dataset --verify vNNN` (проверка наличия manifest.json) для потребителя.
- **T8. Манифест** [FR-007]: поля из спеки; created_at = `datetime.now(UTC)` python-стороны;
  schema из DESCRIBE + null_count is_loft; files sha256 (инкремент из T4, не повторный GET);
  target_populated:false, photo_handling:links. Валидный JSON.
- **T9. Журнал/lock** [FR-011, FR-012]: общий `pipeline_lock_path()`/`process_lock` (не новый
  lock); одна запись stage='export' в try/finally, content_hash=snapshot_id.
- **T10. Фото/0-HTTP** [FR-009, S4, NFR-004]: photo_urls passthrough as-is (не парсим, не
  качаем); security-тест: monkeypatch socket.create_connection/urllib с assert-fail на любой
  внешний хост во время export (кроме MinIO/Trino localhost) — Success #6 буквально.
- **T11. Пустой features** [FR-010]: 0 строк → success с пустыми файлами + манифест row_count=0
  + warn-лог (не отказ; версия валидна, но пустая — явно видно в манифесте). Решение
  зафиксировано.
- **T12. CLI/Make/тесты** [FR-001, FR-014]: `export-dataset --format`; make export-dataset(-demo);
  tests/export unit (манифест, версионинг max+1/пустой→v001, Decimal/timestamp encoder,
  детерминизм-сортировка, vNNN regex, S3Store allowlist) + integration (vNNN в ml-datasets,
  манифест валиден, parquet читается pandas НЕЗАВИСИМО, повтор→v002 без перезаписи, детерминизм
  СОДЕРЖИМОГО на snapshot, 0-HTTP).
- **T13. Документация** [FR-015]: architecture.md += Export (раскладка, манифест frozen,
  I-4-трактовка egress-зоны, детерминизм по содержимому, фото/SSRF, fail-loud, порядок записи,
  инструкция потребителю «проверь manifest.json», snapshot-lineage US-3); Known Risk: PATCH
  устава I-4 (владельцу).

## Units of Work

- **u1-s3-spike** — pyarrow spike (T1), S3Store расширение с allowlist+put_or_fail+list/get (T2)
  [FR-004, FR-013]
- **u2-read-write** — schema (snapshot-пин, T3), writer (потоковый parquet+jsonl+sha256, T4/T5),
  versioning (T6), manifest (T8) [FR-002, FR-003, FR-005, FR-007, FR-008]
- **u3-run-cli** — run.py (единый проход, порядок записи T7, пустой T11, журнал/lock T9), cli,
  фото/0-HTTP (T10) [FR-001, FR-006, FR-009, FR-010, FR-011, FR-012]
- **u4-tests-docs** — тесты unit+integration (T12), Make, architecture.md (T13) [FR-014, FR-015]

## Implementation Steps

1. u1: spike pyarrow (streaming ParquetWriter, arm64/x86 wheel) + S3Store границы; unit
   allowlist/put_or_fail.
2. u2: чтение+запись+версионинг+манифест; unit encoder/версионинг/детерминизм.
3. u3: оркестрация, порядок записи, пустой, журнал; интеграция на живом стеке.
4. u4: полный tests/export, 0-HTTP, независимое чтение parquet; architecture.md; замеры
   NFR-001; полный pytest+ruff+smoke (001-006).

## Files to Create/Modify

Создаются: `src/loftnav/export/{__init__,schema,writer,manifest,versioning,run}.py`,
`tests/export/{unit,integration}/**`. Изменяются: `src/loftnav/io/s3.py` (bucket-параметр
конструктора+allowlist, list/get/put_or_fail), `src/loftnav/config.py` (+ExportConfig),
`src/loftnav/cli.py` (+export-dataset), `pyproject.toml` (+pyarrow пин), `Makefile`,
`docs/architecture.md`. Не трогаются: compose/infra (bucket ml-datasets из 001), харнес,
gold/silver/bronze-код (только чтение features), тесты 001-005.

## Known Risks

1. **PATCH устава I-4 (владельцу)** — Constitution Gate дал PASS (ml-datasets — egress-зона вне
   каталога, симметрична raw, разделение из 001), но текст устава говорит «единственное
   исключение — raw». Рекомендован не-блокирующий PATCH 1.0.0→1.0.1: уточнить на две
   ingress/egress-зоны вне каталога. Решение владельца (Часть III), не входит в scope кода 006.
2. pyarrow совместимость/wheel (C1/C2) — spike T1 первой задачей; точный пин.
3. Streaming-память (P1/P2) — ParquetWriter по чанкам, единый проход (T4); без этого NFR-001
   bounded не выполняется — критично, не implementation detail.
4. list_objects пагинация/CommonPrefixes (C4) — полный скан обязателен (иначе занижение
   max→коллизия vNNN); эмпирически проверить формат ответа MinIO.
5. TOCTOU immutability (S2) — корректность на общем lock (не на guard самом по себе);
   задокументировать; опц. conditional PUT MinIO — при поддержке.
6. Decimal→str в jsonl (C3) — типовое расхождение parquet(decimal)/jsonl(string)
   задокументировать для потребителя.

## Traceability

FR-001→T12/u3 · FR-002→T3/u2 · FR-003→T4/T5/u2 · FR-004→T2/u1 · FR-005→T6/u2 · FR-006→T7/u3 ·
FR-007→T8/u2 · FR-008→T4/u2 · FR-009→T10/u3 · FR-010→T11/u3 · FR-011→T9/u3 · FR-012→T9/u3 ·
FR-013→T1/u1 · FR-014→T12/u4 · FR-015→T13/u4 · NFR-001→T4/шаг4 · NFR-002→T7 · NFR-003→T8 ·
NFR-004→T10 · NFR-005→T1/T2.
