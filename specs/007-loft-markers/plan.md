# Plan 007 — loft-markers

Вход: `spec.md` (с Rollback-секцией). Аудит: `reviews/stage-2-audit.md`.

## Technical Approach

Additive-расширение по слоям с ПЕРВООЧЕРЕДНОЙ задачей — ALTER-эволюция silver (главный риск,
CRITICAL T-1 аудита: текущий ensure_table = только CREATE IF NOT EXISTS; без ALTER пополнение
_SCHEMA сломает MERGE всех источников).

- **T1. ALTER-эволюция silver_writer (первая задача, gate).** По образцу
  `bronze_writer.ensure_table`: DESCRIBE существующей таблицы → diff с `_SCHEMA` →
  `ALTER TABLE ... ADD COLUMN <ident> <type>` на каждую отсутствующую (nullable, идемпотентно).
  Тесты-гварды: (а) merge_rows на существующей таблице после пополнения _SCHEMA не роняет НИ
  ОДИН источник; (б) прогон источника без изменений его .toml после ALTER — зелёный;
  (в) повторный ensure — no-op.
- **T2. Порядок колонок features** [WARN T-2]: три новые колонки вставляются ПЕРЕД
  is_loft/сервисным хвостом (`test_features_columns_frozen` проверяет columns[:6] и
  columns[-1]=="_computed_at" — позиции, не число). Новый тест на точное число колонок
  экспорта (26) — сейчас его нет.
- **T3. Версии схем** [WARN T-3]: bump ОБЕИХ констант — `SILVER_COLUMNS_VERSION` 1→2 и
  `GOLD_COLUMNS_VERSION` 1→2 (консистентность journal-трассировки).
- **T4. Sanity** [T-6]: +2 записи в SANITY_DEFAULTS (ceiling_height_m 1.5–10.0, year_built
  1800–2100); wall_material без диапазона (sanity_ok уже поддерживает).
- **T5. Маппинги** [T-7]: перед правкой .toml — DESCRIBE bronze всех трёх источников
  (подтвердить фактические имена колонок, I-13); затем += поля в 3 конфига (lite — без
  wall_material).
- **T6. Экспорт**: export/schema.py FEATURES_COLUMNS += 3 (тем же порядком, что features).
- **T7. Прогон и замер** [WARN T-4]: `--reprocess` ×3 источника (6050 строк) → build-gold →
  export; wall-clock замер в architecture.md (NFR-001 ≤5 мин — оценка, подтвердить фактом).
- **T8. Документация**: architecture.md — снять gap-запись 004, обновить схемы, замер.

## Units of Work

- **u1-alter-evolution** — T1 + тесты-гварды [FR-001]
- **u2-schema-fields** — T2/T3/T4/T6: _SCHEMA+MAPPABLE_FIELDS+sanity+features+export+версии
  [FR-002, FR-004]
- **u3-mappings-reprocess** — T5: DESCRIBE-подтверждение + 3 .toml + reprocess-прогон
  [FR-003]
- **u4-tests-docs** — T2-тест(26), integration (маркеры заполнены/lite NULL), T7 замер, T8
  [FR-005, FR-006]

## Implementation Steps

1. u1 → полный pytest зелёный (регрессия) ДО остальных правок.
2. u2 → unit-тесты.
3. u3 → reprocess ×3, SELECT-подтверждение маркеров.
4. u4 → build-gold+export, 26 колонок, старые версии нетронуты, замеры, architecture.md,
   полный pytest+ruff+smoke.

## Files to Create/Modify

Изменяются: src/loftnav/transform/silver_writer.py (ALTER-эволюция, +3 поля, bump),
src/loftnav/config.py (+2 sanity), src/loftnav/gold/features.py (+3 перед is_loft, bump),
src/loftnav/export/schema.py (+3), configs/mapping/{apartments,apartments_apartments,
apartments_lite}.toml, tests/{transform,gold,export} (точечно + новые), docs/architecture.md.

## Known Risks

1. **ALTER-эволюция отсутствует** (CRIT T-1 / MUST-FLAG I-8+I-10) → T1 первой задачей с
   тестами-гвардами; Rollback-секция добавлена в спеку. Оба флага сняты этими дополнениями
   (по формулировке самого гейта).
2. Порядок колонок features (T-2) — фикс-тест позиции + новый тест числа.
3. NFR-001 не замерен (T-4) → T7 фактический замер.
4. Имена bronze-колонок не подтверждены DESCRIBE (T-7) → T5 первым шагом u3.

## Traceability

FR-001→T1/u1 · FR-002→T4/u2 · FR-003→T5/u3 · FR-004→T2/T3/T6/u2 · FR-005→T2/u4 · FR-006→T8/u4 ·
NFR-001→T7/u4 · NFR-002→T6/шаг4 · NFR-003→u1/шаг4.
