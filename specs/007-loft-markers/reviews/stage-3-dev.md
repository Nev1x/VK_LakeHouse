# Stage 3 — Dev, отчёт (007-loft-markers)

Дата: 2026-07-22. Исполнитель: kulibin; Tech Lead — основная сессия.

## Результат
Units u1–u4 DONE строго по порядку. u1: ALTER-эволюция silver_writer (DESCRIBE-diff → ADD
COLUMN, по образцу bronze) с 3 тестами-гвардами — ДО пополнения схемы (CRITICAL аудита закрыт).
Маркеры (ceiling_height_m DECIMAL(4,2), wall_material, year_built) в silver+features+export;
SILVER/GOLD_COLUMNS_VERSION bump 1→2; маппинги трёх реальных источников (+DESCRIBE-подтверждение
имён); reprocess 6050 строк; тесты 26-колонок и loft-markers integration.

## Находка и багфикс (bug-handling, маршрутизирован отдельно)
Реальные данные вскрыли pre-existing дефект 004: approx_percentile недетерминирован на группах
400–570 строк (репро 5/5 разных значений; подтверждено Tech Lead независимо 3/3) — нарушение
NFR-004 фичи 004; тест был верен, лгала реализация. Фикс — предодобренный fallback плана 004
T3: точная медиана (array_agg + два центральных, FILTER NULL, чёт/нечёт корректно) в ОБЕИХ
витринах + guard-тесты «нет approx_percentile» + architecture.md root-cause запись. Тайминг не
деградировал (build-gold 8.8с).

## Верификация (двойная)
- kulibin: silver-маркеры заполнены/NULL по схеме; features 6050×26; export v2 26 колонок,
  старые версии immutable (sha); полный цикл 80.5с (NFR ≤300с); determinism ×3; полный pytest
  144 passed; ruff clean; smoke 4 passed.
- Tech Lead независимо: SELECT маркеров (3000/3000/50-c-NULL-wall), DESCRIBE features 26,
  pytest 144 passed БЕЗ deselect, determinism-тест passed, медиана из витрины ×3 идентична.

## Отклонения
Параметризация _merge_sql под честные гвард-тесты (behavior-preserving); гварды на
temp-таблице (валидны до и после пополнения _SCHEMA).
