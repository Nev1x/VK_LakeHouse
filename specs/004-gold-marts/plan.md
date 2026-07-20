# Plan 004 — gold-marts

Вход: `spec.md`. Отчёт аудита: `reviews/stage-2-audit.md`.

## Technical Approach

Пакет `src/loftnav/gold/` (marts, features, run) поверх общих модулей; витрины —
tuple-driven Python-определения SQL (SELECT * структурно невозможен); материализация
build-in-shadow + атомарный swap; полный пересчёт из silver; журнал `stage='build_gold'` со
snapshot_id-привязкой. Техрешения:

- **T1. Spike первой задачей** [FR-005, CRITICAL аудита #1/#2, #5, #13]: на живом Trino 483
  проверить (а) `CREATE OR REPLACE TABLE ... AS SELECT` — атомарность на JDBC-каталоге (иначе
  rename-swap fallback); (б) `approx_percentile(CAST(x AS DOUBLE), 0.5)` — сигнатура и
  повторяемость на фиксированном snapshot (N прогонов, diff); (в) чтение
  `"apartments_clean$snapshots"` — точный синтаксис/квотирование. Результат — в architecture.md
  «Отклонения».
- **T2. Metadata-имя вне ident** [CRITICAL #1]: отдельная функция `snapshots_relation()` —
  базовое имя витрины (frozen-константа) + суффикс `$snapshots` конкатенируются НЕ через
  sanitize_identifier/quote_ident (они отклонят/испортят `$`). ident.py НЕ трогать. Юнит-тест
  на точный SQL snapshot_id-запроса.
- **T3. approx_percentile через CAST** [CRITICAL #2]: медиана — `approx_percentile(CAST(col AS
  DOUBLE), 0.5)`, затем `CAST(... AS DECIMAL(12,2))` на выходе; осознанная потеря точности
  медианы для дашборда — в architecture.md. Если spike покажет нестабильность — точный
  перцентиль через array_agg+ORDER BY (демо-объём выдержит).
- **T4. Явные DECIMAL(p,s) агрегатов** [WARNING #6]: каждая агрегатная колонка витрин — явный
  `CAST(... AS DECIMAL(12,2))` (avg/median цены) / `DECIMAL(8,2)` (площадь); precision/scale
  фиксированы в коде, не выводятся молча CTAS; unit-тест DESCRIBE на точный тип.
- **T5. Определения витрин (tuple-driven)** [FR-002, FR-003, #8]: `marts.py` — каждая витрина =
  (имя, [(колонка, тип, SQL-выражение)], from/group-by); генератор строит явный список колонок;
  unit-тест «нет `*` в сгенерированном SQL».
- **T6. Материализация** [FR-005]: `CREATE TABLE <mart>__build_<run_id> AS SELECT <explicit>`;
  run_id валидируется regex `^[a-f0-9]{32}$` (uuid4.hex) ДО склейки имени (WARNING #3);
  swap: rename old→`__old_<run_id>` → rename build→mart → drop old; либо CREATE OR REPLACE если
  spike подтвердил. Целевая не трогается до swap.
- **T7. Cleanup осиротевших** [WARNING #4]: `SHOW TABLES FROM iceberg.gold` + Python
  `.startswith('<mart>__build_'/'__old_')` (НЕ `LIKE` — `_` там wildcard), паттерн `_bronze_
  sources` 003; в начале прогона и как отдельный шаг.
- **T8. features** [FR-004]: `apartments_features` fv2 (format_version=2), row-level из silver
  (полный rebuild MVP; MERGE-инкремент — кандидат ревизии); is_loft ВСЕГДА NULL (константа, не
  эвристика); photo_urls passthrough; _silver_snapshot_id для манифеста 006.
- **T9. Журнал** [FR-008]: `stage='build_gold'`, одна запись на витрину; content_hash=snapshot_id
  silver (семантика переопределена — decision record в architecture.md #9); не пересекается с
  anti-join transform (stage-фильтр). rows_ok=строк на выходе.
- **T10. Lock** [FR-009]: общий pipeline-lock с ingest/transform.
- **T11. Make/демо/тесты** [FR-011, FR-012]: `make build-gold`, `make build-gold-demo`
  (transform-demo→build-gold); tests/gold/{unit,integration}.
- **T12. Документация** [FR-013]: architecture.md += Gold; уточнить (SHOULD устава):
  time-travel сохраняется в пределах генерации таблицы, DROP old не хранит кросс-прогонную
  историю (SHOULD-1); fv2 = format_version=2 стандарт, не «предыдущая версия контракта»
  (SHOULD-2); явная строка отката (SHOULD-3); is_loft/006-координация (WARNING #7 — decision
  record ДО фиксации схемы); documented-gap лофт-маркеров; ограничения (cross-source count,
  full-scan PERF-4, approx-медиана).

## Units of Work

- **u1-spike-scaffold** — spike (T1), gold-пакет скелет, snapshots_relation (T2),
  bootstrap-проверка namespace [FR-005, FR-014]
- **u2-marts** — marts.py 3 витрины (T3/T4/T5), материализация+swap+cleanup+run_id-валидация
  (T6/T7) [FR-002, FR-003, FR-007]
- **u3-features-journal** — features.py (T8), журнал stage=build_gold (T9), lock (T10)
  [FR-004, FR-008, FR-009]
- **u4-cli-demo-docs** — cli build-gold, пустой-silver путь, Make, тесты, architecture.md
  [FR-001, FR-010, FR-011, FR-012, FR-013]

## Implementation Steps

1. Spike (T1) → зафиксировать стратегию swap/percentile/snapshots.
2. u1 → скелет + snapshots_relation с unit-тестом.
3. u2-marts → integration: витрины непусты, балансы = silver, DESCRIBE типы.
4. u3-features-journal → features стабильна, журнал полон.
5. u4 → build-gold-demo end-to-end, swap-during-read тест, пустой silver, замеры NFR-001,
   architecture.md; полный pytest+ruff+smoke (001-004).

## Files to Create/Modify

Создаются: `src/loftnav/gold/{__init__,marts,features,run}.py`, `tests/gold/{unit,integration}/**`.
Изменяются: `src/loftnav/cli.py`, `src/loftnav/config.py` (+пороги small_sample), `Makefile`,
`docs/architecture.md`. Не трогаются: infra, харнес, ingest/transform-код (только чтение
silver), smoke/ingestion/transform-тесты.

## Known Risks

1. Spike-зависимости (CREATE OR REPLACE атомарность на JDBC, approx_percentile на DECIMAL,
   $snapshots синтаксис) — T1 первой задачей, fallback'и заданы.
2. Детерминизм approx_percentile (WARNING #5) — проверить в spike; при нестабильности — точный
   перцентиль или явный допуск в NFR-004.
3. SHOULD устава #1-3 — уточнения формулировок architecture.md (T12), не поведение.
4. Cross-spec is_loft/006 (WARNING #7) — decision record в architecture.md ДО фиксации схемы;
   ревизия при старте 006.
5. Cross-source дубли инфлируют count, full-scan features/агрегатов — приняты для демо-масштаба
   (наследие PERF-4), документированы.

## Traceability

FR-001→T11/u4 · FR-002→T5/u2 · FR-003→T3/T4/T5/u2 · FR-004→T8/u3 · FR-005→T1/T6/u1/u2 ·
FR-006→T3/u2 · FR-007→T5/u2 · FR-008→T9/u3 · FR-009→T10/u3 · FR-010→u4 · FR-011→T11/u4 ·
FR-012→T11/u2/u4 · FR-013→T12/u4 · FR-014→T2/u1 · NFR-001→шаг5 · NFR-002→T6/T7 · NFR-003→T9 ·
NFR-004→T1/T3 · NFR-005→T2/T6.
