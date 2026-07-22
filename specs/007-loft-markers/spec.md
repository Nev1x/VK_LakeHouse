# Spec 007 — loft-markers (лофт-маркеры в silver и features)

Статус: stage-1 draft → аудит stage-2. Scope: feature. Инициатор: владелец (2026-07-22, при
загрузке реального датасета 6050 квартир).

## Overview

Реальные данные владельца содержат ключевые признаки «лофтовости» — `ceiling_height_m`,
`wall_material`, `year_built` — которые фича 004 честно задокументировала как gap (их не было
в silver-модели). Теперь они есть во входных данных, но отбрасываются нормализацией. 007 —
**additive**-расширение silver.apartments_clean и gold.apartments_features тремя nullable-
колонками + маппинги + версия контрактов. **WHY:** без этих признаков ML-датасет «лофт /
не-лофт» лишён самых сигнальных фич (потолки 3+ м, кирпич, старый фонд = классические маркеры).

## User Stories

- **US-1 Маркеры доезжают до silver.** После transform реального источника колонки
  ceiling_height_m/wall_material/year_built заполнены. _Приёмка:_ SELECT показывает значения
  (потолки 2.5–3.4, материалы, годы 1958–2026) для источника apartments (I-13).
- **US-2 Маркеры в ML-датасете.** export-dataset отдаёт новые колонки в parquet/jsonl;
  манифест несёт обновлённую схему и bump версии контракта. _Приёмка:_ pandas.read_parquet
  видит 26 колонок; manifest.gold_columns_version увеличен; старые версии датасета не тронуты.
- **US-3 Ничего не сломано.** Источники БЕЗ этих полей (apartments_lite не имеет wall_material)
  работают как раньше — новые колонки NULL. _Приёмка:_ transform apartments_lite зелёный;
  все тесты 001–006 зелёные.

## Functional Requirements

- **FR-001 Silver additive.** `ALTER TABLE iceberg.silver.apartments_clean ADD COLUMN` (nullable):
  `ceiling_height_m DECIMAL(4,2)`, `wall_material VARCHAR`, `year_built BIGINT`. Существующие
  строки не переписываются (additive-эволюция, I-6/I-10 expand-only); идемпотентно
  (IF NOT EXISTS-семантика через DESCRIBE-проверку).
- **FR-002 MAPPABLE_FIELDS + sanity.** Три поля добавляются в `MAPPABLE_FIELDS` silver_writer;
  sanity-диапазоны (config.py, документированные): `ceiling_height_m` 1.5–10.0,
  `year_built` 1800–2100; `wall_material` — VARCHAR без диапазона. Вне диапазона → quarantine
  (как price/area).
- **FR-003 Маппинги реального источника.** configs/mapping/{apartments,apartments_apartments}
  .toml += ceiling_height_m (cast decimal), wall_material, year_built (cast bigint);
  apartments_lite.toml += ceiling_height_m, year_built (wall_material в его схеме нет — NULL).
  Изменение конфига → штатный reprocess-протокол 003 (стоп с подсказкой → --reprocess).
- **FR-004 Features additive (bump контракта).** gold/features.py += три колонки (passthrough
  из silver); `GOLD_COLUMNS_VERSION` bump (1→2); export/schema.py `FEATURES_COLUMNS` += те же
  (явный список, не SELECT *). Манифест автоматически несёт новую схему и версию — additive
  по I-6 (устав разрешает additive без мажорной ревизии).
- **FR-005 Тесты.** Обновить существующие (число колонок features/экспорта где захардкожено);
  добавить: unit sanity-диапазонов новых полей; integration — transform реального формата
  даёт заполненные маркеры, lite-источник даёт NULL, экспорт содержит 26 колонок.
- **FR-006 Документация.** architecture.md: снять gap-запись 004 («маркеров нет в данных») →
  колонки добавлены additive v2; отразить в схемах silver/features/manifest.

## Non-Functional Requirements

- **NFR-001.** Полный цикл (reprocess 3 источников 6050 строк + build-gold + export) — ≤5 мин.
- **NFR-002.** Обратная совместимость: потребители старых датасет-версий не затронуты
  (immutable); parquet новых версий читается pandas/pyarrow независимо.
- **NFR-003.** 0 новых зависимостей, 0 новых портов; тесты 001–006 остаются зелёными.

## Authentication & Access

N/A (не затрагивает вход/роли/доступ; та же локальная модель, что 002–006).

## Out of Scope

- Разметка is_loft (остаётся NULL — вне платформы); эвристики по маркерам запрещены (лже-таргет).
- Новые витрины по маркерам (при желании — отдельная фича); living/kitchen_area и прочие
  колонки источника сверх трёх маркеров (по требованию позже, тем же путём).
- Изменение старых версий датасета (immutable).

## Affected Services

Изменяется: src/loftnav/transform/silver_writer.py (+3 поля, ALTER-эволюция), config.py
(+sanity), gold/features.py (+3, bump), export/schema.py (+3), configs/mapping/*.toml (3 файла),
tests (точечно), docs/architecture.md. Не трогается: compose/infra, ingest-код, marts,
манифест-механика (версия — данные, не код), харнес.

## Edge Cases

Источник без полей → NULL (lite); повторный transform без reprocess → стоп по config-hash
(штатный протокол); ceiling 0/отрицательный или year 3000 → quarantine; существующие
silver-строки до ALTER — NULL в новых колонках до reprocess; экспорт старой версии рядом с
новой — разные схемы в манифестах (нормально, версия зафиксирована в каждом).

## Rollback (откат, I-10)

Expand-only изменение: новые колонки nullable, существующие строки не переписываются. Откат
кода = git revert (колонки остаются в таблицах как NULL-ые «сироты» — безвредны, Iceberg
DROP COLUMN возможен вручную при желании, данные не теряются). Откат данных не требуется:
reprocess переигрывает из полного bronze; старые версии датасета immutable. Частичный сбой
ALTER → идемпотентный повтор (DESCRIBE-diff докатывает недостающие).

## Assumptions

- Стек живой, данные владельца загружены (bronze есть); reprocess переиграет silver из bronze
  (данные не теряются — bronze полный).
- DECIMAL(4,2) достаточно для потолков (наблюдаемый диапазон 2.5–3.4).

## Success Criteria

1. `--reprocess` трёх источников: silver 6050 строк, маркеры заполнены у apartments/xlsx,
   NULL у lite (wall_material).
2. build-gold: features 6050 × 26 колонок; export: новая версия с gold_columns_version=2,
   pandas видит новые колонки.
3. Старые датасет-версии нетронуты (sha манифестов не изменились).
4. `pytest -q && ruff check .` зелёные целиком; smoke зелёный.
