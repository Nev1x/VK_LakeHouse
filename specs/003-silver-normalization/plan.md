# Plan 003 — silver-normalization

Вход: `spec.md`. Отчёт аудита: `reviews/stage-2-audit.md`.

## Technical Approach

Пакет `src/loftnav/transform/` (mapping, normalize, dedup, silver_writer, run) поверх общих
модулей платформы; порядок работ строгий: сначала рефакторинги переиспользования с зелёными
тестами 002, потом новый код. Техрешения:

- **T1. Рефакторинги-прекурсоры** [FR-013]: (а) `ident.py` ← sanitize_identifier/
  sanitize_columns/quote_ident из ingest/inference (реэкспорт для обратной совместимости);
  (б) `chunked_insert.py` — единый байт-бюджетный multi-row хелпер (estimate/prefix/chunk),
  на него переводятся bronze_writer, quarantine; (в) `runlog.last_status(conn, content_hash,
  stage)` — обязательный stage-фильтр, **обновить call-site `ingest/run.py` (вызов
  last_status)** — CRITICAL аудита. Regression-gate ДО кода 003: зелёные
  `test_idempotent_repeat_no_growth`, `test_replay_no_duplication`,
  `test_large_rows_no_query_too_large`, `test_oversized_field_reject_valid_json`,
  unit inference/sanitize.
- **T2. MERGE-spike первой задачей** [FR-006]: на живом Trino 483 — `MERGE INTO ... USING
  (VALUES ?,...) ON t.source = ? AND t.source = s.source AND t.external_id = s.external_id`
  (статический bind-предикат на партиционную колонку — partition pruning, аудит #5) с
  bind-параметрами через EXECUTE IMMEDIATE; проверить WHEN MATCHED AND s._ingested_at >
  t._ingested_at THEN UPDATE / WHEN NOT MATCHED INSERT. Результат — в architecture.md.
  Fallback (только при доказанной неподдержке MERGE, не «медленнее»): DELETE+INSERT по
  identity с задокументированным ослаблением атомарности до eventually-consistent-за-чанки
  (аудит #13); anti-join переигрывает партию при crash.
- **T3. Mapping** [FR-002]: `configs/mapping/<источник>.toml`, `tomllib.load(open(path,'rb'))`,
  TOMLDecodeError → читаемое сообщение с файлом/позицией; примитивы: rename, cast,
  unit_convert, regex_replace/extract, `enum_map` — СТРОГО dict exact-match (после
  casefold/trim), НЕ regex (аудит #4); default. Валидация: колонки существуют в bronze-схеме
  (DESCRIBE), два input на одно поле — ошибка, непокрытые колонки — warning.
- **T4. Normalize** [FR-004]: цепочка price/area: str (после regex_replace `,`→`.`) →
  `Decimal(str)` → `.quantize(Decimal('0.01'))` — БЕЗ промежуточного float (аудит #17);
  sanity-диапазоны конфигурируемы (config.py, с комментарием-обоснованием); ReDoS
  defense-in-depth (аудит #1): cap длины значения до regex (`LOFTNAV_REGEX_VALUE_CAP`,
  default 64KB) + чек-лист «нет вложенных квантификаторов» в ревью примитивов + unit-тест с
  патологическим паттерном на bounded-времени.
- **T5. Чтение bronze потоково** [аудит #8]: `cursor.fetchmany(LOFTNAV_TRANSFORM_READ_CHUNK_
  ROWS)` (default 5000) в цикле, НЕ fetchall.
- **T6. Silver DDL** [FR-003]: `WITH (format='PARQUET', format_version=2,
  partitioning=ARRAY['source'])` (точный синтаксис, аудит #19); DDL-smoke: CREATE + DESCRIBE.
- **T7. Идентичность** [FR-005]: id=sha256(f"{source}:{external_id}"); unit-тест
  антиколлизии с `:` в external_id (аудит #15).
- **T8. Инкрементальность/журнал** [FR-007, FR-011]: anti-join с фильтром stage='transform'
  (только success/skipped); запись через runlog как в 002; счётчики честные.
- **T9. Reprocess** [FR-008]: детект mismatch хэша конфига → стоп с подсказкой;
  `--reprocess`: `DELETE WHERE source=?` (partition prune, замер в integration-тесте, аудит
  #10) + полная переигровка источника.
- **T10. Lock** [FR-012]: общий lock-файл с ingest (`loftnav-pipeline.lock`) — переименовать
  существующий с сохранением поведения; deadlock исключён (один мьютекс); грубая
  сериализация — задокументированный компромисс MVP (аудит #14).
- **T11. Демо/Make** [FR-014]: `make transform`, `make transform-demo`; демо-конфиги для
  apartments/flats/listings_flats (вкл. regex_replace запятой, unit_convert, enum_map).
- **T12. Тесты** [FR-015]: unit (примитивы, валидация, Decimal-квантование, ReDoS-cap,
  антиколлизия id, инъекции в значения — `'`/`;`/unicode не ломают MERGE, аудит #2) +
  integration (3 источника → silver; инкрементальность; MERGE-update цены; quarantine;
  reprocess; skip без конфига; конфиг с несуществующей колонкой).
- **T13. Документация** [FR-016]: architecture.md += Transform: схема (frozen), конфиги,
  инкрементальность/reprocess, I-2-трактовки, расширение PERF-4 на transform (аудит #9),
  merge-on-read/компакция вне MVP (аудит #6/#20), fallback-семантика если применён (аудит #13).

## Units of Work

- **u1-refactors** — ident.py, chunked_insert.py, runlog stage-фильтр + call-site ingest,
  lock-переименование; регрессия 002 зелёная [FR-012, FR-013]
- **u2-mapping-normalize** — mapping.py, normalize.py, dedup.py + unit-тесты [FR-002, FR-004,
  FR-005]
- **u3-silver-write** — spike MERGE, silver_writer.py, инкрементальность, reprocess, журнал
  [FR-003, FR-006, FR-007, FR-008, FR-011]
- **u4-cli-demo-docs** — cli transform, quarantine-путь, skip-путь, Make, демо-конфиги,
  тесты integration, architecture.md [FR-001, FR-009, FR-010, FR-014, FR-015, FR-016]

## Implementation Steps

1. u1-refactors → полный `pytest -q` зелёный (регрессия 002) ДО любого кода 003.
2. Spike MERGE (T2) → зафиксировать стратегию.
3. u2-mapping-normalize → unit-тесты.
4. u3-silver-write → integration на живом стеке.
5. u4-cli-demo-docs → `make transform-demo` end-to-end, приёмка Success Criteria, замеры
   NFR-001 (≤60с демо; ≤15с пустой инкремент).

## Files to Create/Modify

Создаются: `src/loftnav/ident.py`, `src/loftnav/chunked_insert.py`,
`src/loftnav/transform/{__init__,mapping,normalize,dedup,silver_writer,run}.py`,
`configs/mapping/*.toml`, `tests/transform/{unit,integration}/**`,
`tests/fixtures/transform/**`. Изменяются: `src/loftnav/ingest/inference.py` (реэкспорт),
`src/loftnav/ingest/bronze_writer.py`, `src/loftnav/quarantine.py` (общий хелпер),
`src/loftnav/runlog.py` (+stage), `src/loftnav/ingest/run.py` (call-site + lock-имя),
`src/loftnav/cli.py`, `Makefile`, `docs/architecture.md`, `src/loftnav/config.py` (+лимиты).

## Known Risks

1. Рефакторинг ломает 002 (CRIT аудита) → порядок «u1 → зелёная регрессия → код 003»,
   явные тесты-гварды перечислены в T1.
2. MERGE-поддержка/производительность — spike T2 первой задачей; fallback с ослабленной
   атомарностью только при доказанной неподдержке.
3. ReDoS патологических regex — cap значения + ревью-чек-лист + unit-тест (T4).
4. Full-scan журнала (наследие PERF-4 002) и merge-on-read read-amplification — приняты
   для демо-масштаба, задокументированы (T13).
5. MERGE без партиционного предиката — full-scan таргета; закрыт статическим bind-предикатом
   source (T2).

## Traceability

FR-001→u4 · FR-002→T3/u2 · FR-003→T6/u3 · FR-004→T4/u2 · FR-005→T7/u2 · FR-006→T2/u3 ·
FR-007→T8/u3 · FR-008→T9/u3 · FR-009→u4 · FR-010→u4 · FR-011→T8/u3 · FR-012→T10/u1 ·
FR-013→T1/u1 · FR-014→T11/u4 · FR-015→T12/u2/u4 · FR-016→T13/u4 · NFR-001→шаг5 · NFR-002→T8 ·
NFR-003→T8 · NFR-004→T3/T4 · NFR-005→T3.
