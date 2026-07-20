# Spec 004 — gold-marts (витрины и feature-таблица)

Статус: stage-1 draft → аудит stage-2. Scope: feature. Intent: `specs/004-gold-marts/intent.md`.

## Overview

CLI `loftnav build-gold`: из `silver.apartments_clean` строятся (1) три материализованные
витрины-агрегата для дашбордов 005 и (2) row-level feature-таблица `apartments_features` — вход
006. Механика: Trino SQL + Python-раннер, полный детерминированный пересчёт с атомарной заменой
(build-in-shadow + rename), журнал `stage='build_gold'`, схемы gold — frozen (I-6). **WHY:**
gold — витринный слой; его схемы и имена таблиц захардкодят 005 (Grafana) и 006 (экспорт).

## User Stories

- **US-1 Распределение по районам.** Аналитик 005 видит `gold.mart_price_area_by_district`
  (count, avg/median/min/max цены, avg price/m², avg площадь). _Приёмка:_ SUM(listing_count)
  по районам = COUNT(*) silver на момент пересчёта (I-13); NULL-район → группа `unknown`.
- **US-2 Срезы по стилю/ремонту/мебели.** `gold.mart_style_renovation_furniture` по
  нормализованным (trim/lower) значениям; малые группы (count < порог) видимо помечены.
- **US-3 Динамика загрузок.** `gold.mart_listing_dynamics` по `DATE(_ingested_at)` из silver
  (НЕ из pipeline_runs — I-4): daily + cumulative; пустых дыр в ряду нет.
- **US-4 Стабильная feature-таблица.** 006 читает `gold.apartments_features` с frozen-схемой.
  _Приёмка:_ DESCRIBE одинаков до/после любого пересчёта; каждая строка ссылается на
  `silver.apartments_clean.id`.
- **US-5 Воспроизводимость и наблюдаемость.** Каждый build пишет `stage='build_gold'` в журнал
  (по таблице); конкурентный запуск сериализован (I-15); дашборд никогда не видит
  полу-пересчитанную витрину.

## Functional Requirements

- **FR-001 CLI.** Сабкоманда `loftnav build-gold` в реестре cli.py; флаг `--only <mart>`
  (пересчитать одну витрину). Все витрины по умолчанию.
- **FR-002 Определения витрин как код.** SQL-определения витрин — Python-модули
  `src/loftnav/gold/marts.py` (не runtime-конфиги: набор витрин курируется и frozen по I-6,
  не варьируется конечным пользователем как источники); тестируемая генерация SQL. Явный список
  колонок в каждом SELECT (НЕ `SELECT *` — additive-колонка silver не должна молча просочиться
  и сломать frozen-схему gold).
- **FR-003 Витрины (frozen, additive-only).**
  `iceberg.gold.mart_price_area_by_district`: `district` (COALESCE→'unknown'), `listing_count`,
  `avg_price_rub` DECIMAL, `median_price_rub`, `min/max_price_rub`, `avg_price_per_m2`,
  `avg_area_m2`, `_computed_at`, `_gold_run_id`.
  `iceberg.gold.mart_style_renovation_furniture`: `style_norm`, `renovation_style_norm`,
  `has_renovation`, `has_furniture`, `listing_count`, `avg_price_rub`, `median_price_rub`,
  `avg_area_m2`, `is_small_sample` BOOLEAN (count < `LOFTNAV_GOLD_SMALL_SAMPLE`, default 3),
  `_computed_at`, `_gold_run_id`.
  `iceberg.gold.mart_listing_dynamics`: `load_date` DATE, `listings_added`,
  `listings_added_cumulative`, `_computed_at`, `_gold_run_id`.
  Деление на ноль: `price_per_m2` через `NULLIF(area_m2, 0)` — gold защищается сам (003 не
  гарантирует area>0, только присутствие; I-13 — проверить, не поверить).
- **FR-004 apartments_features (frozen, вход 006).** `iceberg.gold.apartments_features`
  (fv2): `id`, `source`, `external_id` VARCHAR; `price_rub` DECIMAL(12,2), `area_m2`
  DECIMAL(8,2), `price_per_m2` DECIMAL(12,2) nullable (NULL при area=0); `rooms`, `floor`,
  `floors_total`, `metro_minutes` BIGINT; `floor_ratio` DOUBLE nullable (NULL при
  floors_total NULL/0); `district`, `style`, `renovation_style` VARCHAR; `has_renovation`,
  `has_furniture` BOOLEAN; `listed_at` TIMESTAMP; `photo_urls` VARCHAR (JSON as-is,
  passthrough для CV-фич 006, gold не парсит); `is_loft` BOOLEAN nullable — **target-заготовка,
  ВСЕГДА NULL** на выходе (разметка — вне платформы; эвристика `style ILIKE '%loft%'`
  ЗАПРЕЩЕНА как лже-таргет/утечка, I-11); служебные `_silver_snapshot_id`,
  `_source_transform_run_id`, `_gold_run_id` VARCHAR, `_computed_at` TIMESTAMP.
- **FR-005 Материализация build-in-shadow + atomic swap.** Каждая витрина: `CREATE TABLE
  <mart>__build_<run_id> AS SELECT ...` → `ALTER TABLE <mart> RENAME TO <mart>__old_<run_id>`
  (если существует) → `ALTER TABLE <mart>__build_<run_id> RENAME TO <mart>` → `DROP old`.
  Целевая таблица во время пересчёта не трогается (I-8: чтение дашборда не блокируется).
  Spike: проверить `CREATE OR REPLACE TABLE ... AS SELECT` на Trino 483 — если атомарен,
  использовать как упрощение; иначе rename-swap (fallback по умолчанию).
- **FR-006 Полный пересчёт (I-2-трактовка).** Все витрины и features — полный rebuild из silver
  каждый прогон (агрегаты — функция всей выборки; инкрементальный агрегат с медианой некорректен
  без хранения распределения). Это штатный режим ПРОИЗВОДНОГО слоя, не «переписывание источника
  без решения владельца»: gold детерминированно вычислим из silver, Iceberg-снапшоты витрин не
  expire (time-travel сохраняется). Фиксируется в architecture.md как трактовка (аналог
  reprocess 003). Переход features на инкрементальный MERGE — кандидат ревизии при росте.
- **FR-007 Нормализация в агрегатах.** style/renovation_style группируются по
  `lower(trim(...))` (иначе «Лофт»/«loft» дробят сегмент); COALESCE NULL→'unknown'/'none' с
  явной меткой.
- **FR-008 Журнал.** Одна запись `stage='build_gold'` на витрину: `target_table`=имя витрины,
  `content_hash`=snapshot_id silver на старте build (через
  `apartments_clean$snapshots` ORDER BY committed_at DESC LIMIT 1 — точная воспроизводимая
  привязка «на каком состоянии silver построено», без хэша миллионов строк),
  `rows_ok`=строк на выходе, `schema_json`={gold_columns_version}, один INSERT в try/finally,
  честные счётчики.
- **FR-009 Конкурентность.** Общий pipeline-lock (с ingest/transform): build-gold не идёт
  параллельно с ними и с собой (I-15).
- **FR-010 Пустой silver.** Валидная пустая витрина, `success` rows_ok=0, не падение (I-8);
  дашборд покажет «нет данных».
- **FR-011 Make/демо.** `make build-gold`, `make build-gold-demo` (= transform-demo →
  build-gold, полная цепочка ingest→gold для QA 005/006).
- **FR-012 Тесты.** `tests/gold/unit/` (генерация SQL витрин, NULLIF-защита, нормализация,
  snapshot_id-запрос) + `tests/gold/integration/` (requires_stack): build-gold после
  transform-demo → витрины непусты и балансы сходятся с silver; features-схема стабильна;
  swap не роняет чтение старой таблицы; пустой silver → пустые витрины; повторный build
  идемпотентен по содержимому.
- **FR-013 Документация.** architecture.md += Gold: схемы витрин и features (frozen),
  материализация/swap, I-2-трактовка полного пересчёта, content_hash=snapshot_id,
  documented-gap лофт-маркеров, риск утечки через style, ограничения (cross-source дубли
  инфлируют count — наследие 003).
- **FR-014 Переиспользование.** trino_client, ident.quote_ident, runlog, bootstrap
  (iceberg.gold уже в MEDALLION_NAMESPACES) — без изменений; chunked_insert/quarantine на этом
  слое не нужны (CTAS/INSERT..SELECT стримит сам Trino; агрегатных «браков» нет).

## Non-Functional Requirements

- **NFR-001 Производительность.** `make build-gold` на демо-объёме — ≤30с все витрины;
  отдельная витрина — ≤10с; окно неконсистентности при swap — миллисекунды (rename метаданных,
  не CTAS-длительность).
- **NFR-002 Надёжность.** Сбой на витрине → журнал failed по этой витрине + продолжение
  остальных; build-shadow не оставляет целевую в битом состоянии (swap атомарен); осиротевшие
  `__build_`/`__old_` временные таблицы вычищаются (в т.ч. при рестарте — по префиксу).
- **NFR-003 Наблюдаемость.** 100% витрин прогона в журнале; snapshot_id привязка;
  structured-логи с run_id.
- **NFR-004 Воспроизводимость.** Тот же silver-snapshot → тот же выход витрин (детерминизм —
  критерий DoD 004).
- **NFR-005 Безопасность/сопровождаемость.** 0 новых зависимостей, 0 новых портов; SQL —
  идентификаторы через ident, значения (run_id, snapshot_id, пороги) — bind-параметрами;
  новая витрина = новый Python-модуль + версия контракта.

## Authentication & Access

Локальный CLI от владельца; Trino — `loftnav`/`TRINO_PASSWORD` (HTTPS:8443); MinIO не
затрагивается напрямую (gold пишет Iceberg-таблицы через Trino). Новых поверхностей/портов/ролей
нет. SSO отсутствует (устав v1.0.0).

## Out of Scope

- Обучение/разметка ML-модели, реальный `is_loft` (вне платформы, устав/intent 006); эвристика
  метки — запрещена (лже-таргет).
- Фото-фичи/CV (это 006); gold отдаёт photo_urls passthrough.
- Дашборды Grafana (005); экспорт датасета (006).
- Предвычисленные перцентили про запас, витрина под каждый срез, инкрементальные агрегаты,
  геокодинг, near-real-time планировщик.

## Affected Services

Изменяется: `src/loftnav/` (+`gold/` пакет: marts, features, run; правки cli.py, config.py
+пороги), `Makefile`, `docs/architecture.md`, `tests/gold/**`. Не затрагивается: compose/infra,
харнес, raw/bronze/silver-код (только чтение silver), tests/smoke, tests/ingestion,
tests/transform (обязаны остаться зелёными).

## Edge Cases

Пустой silver → пустые витрины (FR-010); район/стиль NULL → 'unknown'/'none' группа; area=0 →
price_per_m2 NULL (NULLIF); floors_total 0/NULL → floor_ratio NULL; малая выборка (n=1-2) →
is_small_sample=true (не тонет как «точная» цифра); silver additive-колонка → gold не ломается
(явный список колонок); cross-source дубли → инфлируют count (наследие 003, документировано);
пересчёт во время чтения дашбордом → атомарный swap; сбой на 1 из витрин → остальные считаются;
осиротевшие временные таблицы после краша → вычистить по префиксу.

## Assumptions

- Стек и silver 003 живы (`make transform-demo` прогнан, apartments_clean непуста).
- `CREATE OR REPLACE TABLE`/`ALTER RENAME`/`$snapshots`/`approx_percentile` поддержаны Trino 483
  для Iceberg — spike первой задачей (методология 002/003); rename-swap — документированный
  fallback.
- Демо-цепочка build-gold-demo воспроизводит данные для QA 005/006.

## Success Criteria

1. `make build-gold-demo`: три витрины + apartments_features непусты; SUM(count по районам) =
   COUNT(*) silver; SELECT-подтверждение через Trino (I-13).
2. Повторный build → то же содержимое (детерминизм на том же snapshot); дашборд-читатель во
   время swap видит консистентную таблицу (integration-тест).
3. `DESCRIBE apartments_features` стабилен; is_loft — всегда NULL; price_per_m2 NULL при area=0.
4. Пустой silver → пустые витрины, success rows_ok=0, не падение.
5. Журнал `stage='build_gold'` по каждой витрине с snapshot_id и rows_ok.
6. `pytest -q && ruff check .` зелёные (001-004); smoke зелёный; secret-скан зелёный.
