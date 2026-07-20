# Stage 3 — Dev, отчёт (004-gold-marts)

Дата: 2026-07-20. Исполнитель: kulibin; Tech Lead — основная сессия.

## Результат
Units u1–u4 DONE. Spike выбрал CREATE OR REPLACE TABLE AS SELECT (атомарен на JDBC-каталоге,
нет not-found окна rename-swap, time-travel сохраняется) + approx_percentile(CAST DOUBLE)
стабилен ×5 + snapshot-пин FOR VERSION AS OF для детерминизма. 3 витрины (district/style/
dynamics) + apartments_features, tuple-driven (SELECT * невозможен), явные CAST DECIMAL(p,s),
NULLIF-защита, is_loft NULL-константа, журнал stage=build_gold с content_hash=snapshot_id.

## Решения/отклонения
1. CREATE OR REPLACE вместо rename-swap (spike подтвердил атомарность — строго лучше);
   prefix-cleanup оставлен как защита от легаси-крашей, run_id всё равно валидируется.
2. $snapshots-имя — отдельная snapshots_relation(), не через ident (сохранён строгий санитайзер).

## Верификация (двойная)
- kulibin: build-gold-demo (district 5/style 5/dynamics 1/features 11), баланс
  SUM(listing_count)=11=silver count, is_loft все NULL, price_per_m2 NULL при area=0, swap-during-
  read 0 ошибок, пустой silver → 0 строк без падения, 98 passed, build-gold 10с.
- Tech Lead независимо: pytest 98 passed, ruff clean, smoke 4 passed; SHOW TABLES 4 gold-таблицы;
  SELECT баланс 11=11; features 11 строк, 0 non-null is_loft.

## Хвосты → stage-4/бэклог
is_loft/006 координация; cross-source дубли инфлируют count; approx-медиана; full-scan
(PERF-4); silver содержит тестовую примесь (11 vs демо-6, на баланс gold не влияет).
