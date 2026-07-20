# Stage 3 — Dev, отчёт (003-silver-normalization)

Дата: 2026-07-20. Исполнитель: kulibin (с восстановлением после обрыва API-сессии: состояние
перепроверено по git/pytest, ложная память о готовом silver_writer отброшена — I-13);
Tech Lead — основная сессия.

## Результат
Units u1–u4 DONE строго по порядку (u1-рефакторинги → регрессия 002 зелёная 44 passed → spike
→ код 003). Spike: MERGE INTO с bind-VALUES и партиционным предикатом работает на Trino 483
fv2 — fallback не нужен. Silver: apartments_clean (DECIMAL-цены/площади, partition by source),
6 демо-строк из 3 источников с разными единицами; инкрементальность 0-партий на повторе;
MERGE-update цены без дубля; quarantine с балансом; reprocess по явному флагу; skip источников
без конфига.

## Решения/отклонения
1. Демо-источники t_avito/t_cian/t_domclick (фикстуры 002 не имеют обязательных price+area);
   источники 002 демонстрируют FR-010 skip.
2. id: length-prefix sha256(len(source):source:external_id) — инъективность при ':' в
   external_id.
3. partial терминален для transform (повтор partial копил бы rejects) — дефект найден и
   закрыт в цикле.
4. MERGE USING SELECT CAST(...) FROM (VALUES...) — типизация при all-NULL колонках.
5. dev-reset синтетики silver/rejects/transform-записей журнала при приёмке (до реальных
   данных; штатная работа append-only).

## Верификация (двойная)
- kulibin: transform-demo end-to-end (единицы тыс/руб/млн сходятся), повтор 7с/0 партий,
  MERGE-update 5000000→6000000 при count==distinct==6, quarantine 2+1=3, reprocess-протокол,
  74 passed/ruff/smoke.
- Tech Lead независимо: pytest 74 passed, ruff clean, smoke 4 passed; SELECT silver: 6/6
  distinct, Decimal-значения корректны; хвост незакрытого config-mismatch t_domclick закрыт
  штатным --reprocess; контрольный make transform — все success/skipped, 0 новых партий.

## Хвосты → stage-4/бэклог
Cross-source дедуп (Out of Scope), PERF-4 расширен на transform, merge-on-read компакция,
PII quarantine, синтетический external_id — документированные ограничения.
