# Spec 003 — silver-normalization (единая silver-таблица квартир)

Статус: stage-1 draft → аудит stage-2. Scope: feature. Intent: `specs/003-silver-normalization/intent.md`.

## Overview

CLI `loftnav transform`: разношёрстные bronze-таблицы → единая
`iceberg.silver.apartments_clean` по декларативным TOML-маппингам per-источник (новый источник
= конфиг, не код — доменная ловушка №1 устава). Приведение типов/единиц, дедупликация
объявлений внутри источника (MERGE, last-write-wins), инкрементальность по content_hash через
журнал, quarantine непрошедших нормализацию, явный reprocess при смене конфига. **WHY:**
silver — вход 004 (gold) и транзитивно 006; схема apartments_clean становится frozen-контрактом.

## User Stories

- **US-1 Единая схема.** ≥3 bronze-источников с разными схемами → один `apartments_clean`
  (цена в руб, площадь в м²) одним прогоном; новый источник добавляется только TOML-файлом.
  _Приёмка:_ SELECT показывает строки всех источников с едиными колонками (I-13).
- **US-2 Источник без конфига не теряется молча.** Явный skip с записью журнала и логом,
  отличимый от quarantine. _Приёмка:_ статус виден в journal/логе (I-9), в silver ничего не
  попало.
- **US-3 Идемпотентная инкрементальность.** Повторный transform после нового ingest
  обрабатывает только новые bronze-партии; дублей identity нет. _Приёмка:_
  `COUNT(*) = COUNT(DISTINCT source, external_id)`; второй прогон не перечитывает всё (журнал).
- **US-4 Quarantine нормализации.** Битые строки (цена 0, площадь вне диапазона, невалидное
  число) → `iceberg.quarantine.silver_<источник>_rejects` с причиной; остальные строки
  источника проходят (I-8). _Приёмка:_ статус partial, балансы сходятся.
- **US-5 Дедуп и версии.** Повторная публикация того же `source+external_id` с новой ценой
  обновляет строку (не дубль); побеждает поздний `_ingested_at`. _Приёмка:_ count стабилен,
  цена обновлена. Cross-source дедуп НЕ гарантируется (ограничение зафиксировано).

## Functional Requirements

- **FR-001 CLI.** Сабкоманда `loftnav transform` в существующем реестре cli.py; флаги:
  `--source <имя>` (только один источник), `--reprocess <имя>` (переигровка источника, FR-008).
- **FR-002 Маппинг-конфиги.** `configs/mapping/<источник>.toml` (tomllib — stdlib, 0 новых
  зависимостей). Закрытый набор декларативных примитивов: `rename`, `cast`,
  `unit_convert(from,to)` (тыс_руб→руб, сотка→м2 и т.п.), `regex_replace`/`regex_extract`,
  `enum_map`, `default`. НИКАКОГО eval/exec произвольного кода (I-7/I-14). Строгая валидация
  при старте (fail fast, читаемые ошибки): обязательные ключи, input-колонка существует в
  bronze-схеме, два input на одно silver-поле — конфликт; непокрытые конфигом bronze-колонки —
  warning в лог (не ошибка).
- **FR-003 Silver-схема (frozen для 004/006, additive-only).**
  `iceberg.silver.apartments_clean` (`format='PARQUET', format_version=2`,
  `partitioning=['source']`): `id` VARCHAR (sha256 от `source:external_id`), `source`,
  `external_id` VARCHAR; `price_rub` DECIMAL(12,2), `area_m2` DECIMAL(8,2) (деньги/площадь —
  точная арифметика для агрегатов 004); `rooms`, `floor`, `floors_total`, `metro_minutes`
  BIGINT; `address`, `district`, `style`, `renovation_style` VARCHAR; `has_renovation`,
  `has_furniture` BOOLEAN; `photo_urls` VARCHAR (JSON-массив as-is); `listed_at` TIMESTAMP;
  служебные: `_source_run_id`, `_source_content_hash`, `_mapping_config_hash` VARCHAR,
  `_ingested_at`, `_transformed_at` TIMESTAMP, `_transform_run_id` VARCHAR. Обязательность
  (id/source/external_id/price_rub/area_m2) — через quarantine, не SQL-constraint; остальное
  nullable.
- **FR-004 Нормализация.** Приведение единиц по конфигу; запятая-десятичная → точка ДО cast
  (наследие контракта 002); документированные конфигурируемые sanity-диапазоны (price_rub > 0,
  1 ≤ area_m2 ≤ 1000, rooms ≤ 20 и т.п. — дефолты в config.py с пояснением, не magic numbers);
  нарушение → quarantine с конкретной причиной.
- **FR-005 Идентичность.** `external_id` — из конфига источника; нет стабильного id →
  синтетический хэш нормализованных полей (документированная best-effort деградация:
  переиндексация при правке текста). Intra-source дедуп гарантируется; cross-source — нет
  (Out of Scope).
- **FR-006 Запись MERGE (I-7, I-15).** `MERGE INTO apartments_clean USING (VALUES ...) ON
  (source, external_id)`: WHEN MATCHED AND новый `_ingested_at` новее → UPDATE, WHEN NOT
  MATCHED → INSERT. Значения — только bind-параметрами; чанки по бюджету длины SQL-текста
  (общий хелпер FR-013, урок 002). _I-2-трактовка:_ точечный ACID-upsert по known identity ≠
  переписывание таблицы (аналог replay 002); bulk-перезапись — только FR-008 явным флагом.
- **FR-007 Инкрементальность.** Anti-join: bronze `_content_hash`, отсутствующие в журнале
  `stage='transform'` со статусом success/skipped → обрабатываются; остальные пропускаются.
  Bounded scan (I-15). Полный пересчёт — НЕ default.
- **FR-008 Reprocess при смене конфига.** Хэш TOML-конфига пишется в `_mapping_config_hash`
  строк и в `schema_json` журнала. При несовпадении текущего хэша с последним успешным —
  transform источника ОСТАНАВЛИВАЕТСЯ с читаемой ошибкой и подсказкой запустить
  `loftnav transform --reprocess <источник>`; reprocess = `DELETE FROM apartments_clean WHERE
  source = ?` (bind) + полная переигровка всех bronze-партий источника. _I-2:_ явное действие
  оператора (сам флаг — решение), журнал append-only получает новые записи.
- **FR-009 Quarantine.** Через общий `quarantine.py` (`layer='silver'`) →
  `iceberg.quarantine.silver_<источник>_rejects`; причины человекочитаемы; балансы честные
  (счётчики = фактически закоммиченное, урок 002).
- **FR-010 Источник без конфига.** Bronze-таблицы без TOML — журнальная запись
  `status='skipped'` + лог-предупреждение; НЕ quarantine, НЕ тихий пропуск.
- **FR-011 Журнал.** Одна запись `stage='transform'` на (источник × bronze content_hash):
  `content_hash`=bronze-хэш, `target_table='iceberg.silver.apartments_clean'`,
  `schema_json`={mapping_config_hash, silver_columns_version}; один INSERT в try/finally,
  честные счётчики.
- **FR-012 Конкурентность.** ЕДИНЫЙ файловый lock с ingest (общее имя lock-файла): transform
  не идёт параллельно ни с ingest, ни с другим transform (I-15).
- **FR-013 Рефакторинги переиспользования (без изменения поведения 002).**
  (а) санитайзер/квотер → нейтральный `src/loftnav/ident.py` (из ingest/inference);
  (б) общий байт-бюджетный multi-row хелпер `src/loftnav/chunked_insert.py` — используют
  bronze_writer, quarantine, silver_writer; (в) `runlog.last_status(..., stage=...)` — фильтр
  по стадии (иначе ingest/transform-записи с одним hash путаются). Тесты 002 остаются зелёными.
- **FR-014 Make/демо.** `make transform`, `make transform-demo`; демо-конфиги
  `configs/mapping/` для фикстурных источников 002 (apartments, flats, listings_flats).
- **FR-015 Тесты.** `tests/transform/unit/` (примитивы, unit_convert, sanity, валидация
  конфига, dedup-ключ) + `tests/transform/integration/` (requires_stack): 3 источника → один
  silver; инкрементальная идемпотентность; MERGE-обновление цены; quarantine; reprocess;
  источник без конфига; конфиг с несуществующей колонкой.
- **FR-016 Документация.** architecture.md += Transform: схема apartments_clean (frozen),
  формат конфигов, инкрементальность/reprocess, I-2-трактовка MERGE/reprocess, ограничения
  (cross-source, полнота полей по источникам).

## Non-Functional Requirements

- **NFR-001 Производительность.** Демо-набор (3 источника 002) — ≤60с; инкрементальный прогон
  по неизменённому bronze — ≤15с (только anti-join, 0 обработанных партий); MERGE-чанки в
  бюджете ≤700K символов SQL-текста.
- **NFR-002 Надёжность.** Сбой посреди источника → журнал с фактическими счётчиками +
  error_message; повторный запуск дообрабатывает партию корректно (MERGE идемпотентен по
  identity).
- **NFR-003 Наблюдаемость.** 100% партий в журнале; rows_ok+rows_quarantined = обработанные
  строки; structured-логи с run_id.
- **NFR-004 Безопасность.** 0 новых зависимостей (tomllib), 0 новых портов; SQL — только
  bind-параметры + санитизированные идентификаторы (дисциплина 002).
- **NFR-005 Сопровождаемость.** Новый источник = 1 TOML-файл; новый примитив трансформации =
  именованная функция через код-ревью (не eval).

## Authentication & Access

Как 002: локальный CLI от владельца; Trino — `loftnav`/`TRINO_PASSWORD` (HTTPS:8443), MinIO не
затрагивается (transform не ходит в raw). Новых поверхностей доступа/портов/ролей нет. SSO
отсутствует (устав v1.0.0).

## Out of Scope

- Cross-source дедуп (fuzzy/ML-matching) — ограничение зафиксировано; кандидат рядом с 006.
- SCD-историчность silver (версии объявления во времени); геокодинг адресов (внешние API
  запрещены I-1); DSL произвольных выражений/eval; config-management UI/hot-reload.
- Агрегаты и features (004); дашборды (005); экспорт (006).
- Сложное партиционирование/sort beyond `source`.

## Affected Services

Изменяется: `src/loftnav/` (+`transform/` пакет: mapping, normalize, dedup, silver_writer,
run; +`ident.py`, +`chunked_insert.py`; правки: cli.py (+сабкоманда), runlog.py (stage-фильтр),
bronze_writer/quarantine (переход на общий хелпер), bootstrap.py (silver-таблица не в
bootstrap — создаёт silver_writer)), `configs/mapping/*.toml` (новая директория), `Makefile`,
`docs/architecture.md`, `tests/transform/**`, `tests/fixtures/transform/**`.
Не затрагивается: compose/infra, харнес, raw bucket, tests/smoke и tests/ingestion (обязаны
остаться зелёными — FR-013).

## Edge Cases

Bronze-источник без конфига (skip, FR-010); конфиг ссылается на несуществующую колонку (fail
fast с именем колонки); непокрытые новые bronze-колонки (warning); `"1234,56"` VARCHAR →
regex_replace+cast; цена 0/отрицательная, площадь вне диапазона → quarantine; external_id
пустой при заданном в конфиге → quarantine; повторный transform без новых данных → 0 партий,
быстрый выход; смена конфига → стоп с подсказкой reprocess; конкурентный запуск → lock-ошибка;
reprocess при живых читателях (005) — MERGE/DELETE атомарны на снапшот Iceberg.

## Assumptions

- Стек и данные 002 живы (`make ingest-demo` прогнан); контракты 002 действуют.
- MERGE INTO поддержан Trino 483 для Iceberg fv2 — проверяется spike'ом до массового кода
  (аналогично spike 002; при неподдержке — fallback DELETE+INSERT по identity в план-ревизию).
- Демо-конфиги пишутся под фикстурные источники 002; реальные источники владелец опишет
  конфигами позже.

## Success Criteria

1. `make transform-demo`: строки всех трёх фикстурных источников в `apartments_clean` с
   едиными типами (DECIMAL-цена в рублях и т.д.), SELECT-подтверждение (I-13).
2. Повторный прогон: 0 новых партий, count и содержимое стабильны (инкрементальность).
3. Обновление цены в повторно загруженном объявлении → MERGE-update, не дубль.
4. Битые строки в `silver_*_rejects` с причинами; балансы сходятся.
5. Смена демо-конфига → стоп с подсказкой; `--reprocess` переигрывает источник; журнал полон.
6. `pytest -q && ruff check .` зелёные (вкл. все тесты 001/002); smoke зелёный; secret-скан
   зелёный.
