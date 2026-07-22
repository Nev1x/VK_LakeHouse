# Pipeline Audit — append-only журнал (пишет только scripts/pipeline-state.sh)

| ts (UTC) | event | detail |
|---|---|---|
| 2026-07-22T14:18:16Z | init | scope=feature · Лофт-маркеры: additive-расширение silver.apartments_clean и gold.apartments_features колонками ceiling_height_m, wall_material, year_built (+ маппинги реального источника apartments); версия контрактов bump |
| 2026-07-22T14:18:17Z | stage-1-creative:start | - |
| 2026-07-22T14:19:34Z | confidence:stage-1-creative | level=green reason=spec-lint OK 10/10; компактный stage-1 (deviation в learnings), полный аудит на stage-2 |
| 2026-07-22T14:19:34Z | stage-1-creative:done | - |
| 2026-07-22T14:19:36Z | stage-2-audit:start | - |
| 2026-07-22T14:27:42Z | agent:audit:done | техаудит CRIT 1 (silver_writer без ALTER-эволюции — сломал бы MERGE всех источников), WARN 3, INFO 4; constitution MUST-FLAG 2 (I-8/I-10 — грани того же T-1), снимаются добавлением ALTER-задачи в план + Rollback в спеку |
| 2026-07-22T14:28:51Z | constitution-gate | MUST-FLAG: 0 · SHOULD-FLAG: 0 · NEEDS-INFO: 0 |
| 2026-07-22T14:28:53Z | units-set | u1-alter-evolution,u2-schema-fields,u3-mappings-reprocess,u4-tests-docs |
| 2026-07-22T14:28:55Z | user-approval | approved by Owner (delegated; инициатор фичи, выбор «Сделать сейчас» 2026-07-22) |
| 2026-07-22T14:28:56Z | confidence:stage-2-audit | level=green reason=spec-lint OK, plan-lint OK (9/9, 0 overreach), MUST-FLAG'и сняты дополнениями по формулировке гейта; approve по делегации (владелец — инициатор) |
| 2026-07-22T14:28:56Z | stage-2-audit:done | - |
| 2026-07-22T14:28:59Z | stage-3-dev:start | - |
| 2026-07-22T14:29:01Z | agent:kulibin:start | stage-3: ALTER-эволюция silver первой задачей, потом поля/маппинги/reprocess |
| 2026-07-22T15:04:44Z | agent:kulibin:done | u1-u4 DONE: ALTER-эволюция silver с 3 гвардами, 26 колонок features/export, reprocess 6050 строк 80.5с (NFR x3.7 запас), маркеры заполнены/NULL по схеме, v044 gold_columns_version=2, старые версии immutable; НАХОДКА: pre-existing недетерминизм approx_percentile на реальных данных (root cause доказан) — маршрутизирован багфиксом 004 |
| 2026-07-22T15:04:45Z | agent:kulibin:start | багфикс 004 по bug-handling: точная медиана (fallback плана 004 T3), guard от регрессии |
| 2026-07-22T15:14:16Z | unit-done | u1-alter-evolution |
| 2026-07-22T15:14:18Z | unit-done | u2-schema-fields |
| 2026-07-22T15:14:20Z | unit-done | u3-mappings-reprocess |
| 2026-07-22T15:14:22Z | unit-done | u4-tests-docs |
| 2026-07-22T15:14:24Z | agent:kulibin:done | багфикс 004: точная медиана array_agg (fallback плана T3), determinism-тест x3 зелёный, полный pytest 144 passed БЕЗ deselect, build-gold 8.8с |
| 2026-07-22T15:14:25Z | confidence:stage-3-dev | level=green reason=сам прогнал: pytest 144 passed БЕЗ deselect, ruff clean, determinism x3 (тест+витрина), SELECT маркеров, features 26; units 4/4 |
| 2026-07-22T15:14:25Z | stage-3-dev:done | - |
| 2026-07-22T15:14:47Z | stage-4-quality:start | checkpoint=769edbc9c1f0faacf9e7cbf38747b2d55d9fd906 |
| 2026-07-22T15:14:51Z | agent:qa-verifier:start | адверсарная проверка 007 + багфикса медианы |
| 2026-07-22T15:27:08Z | agent:qa-verifier:done | PASS проход 1: CRIT 0 WARN 0 INFO 1; ALTER только из _SCHEMA (инъекция не пролезла), sanity-границы инклюзивны, медиана x5 + ручная сверка чёт/нечёт, v035 immutable по sha, 144 passed x2 |
| 2026-07-22T15:27:09Z | quality-head | 8113d9fc6f6785235f6cea97dd16f87b77fc0735 |
| 2026-07-22T15:27:18Z | quality-verdict | PASS — matrix 13/13 DONE + багфикс медианы; pytest 144 passed целиком x2 + ruff clean + smoke 4 passed; адверсарно CRIT 0 WARN 0: ALTER из _SCHEMA, sanity-границы, медиана-детерминизм x5 с ручной сверкой, immutable v035 по sha; retry 0 |
| 2026-07-22T15:27:23Z | confidence:stage-4-quality | level=green reason=вердикт PASS; сигналы прогнаны лично (pytest 144/ruff/determinism/SELECT маркеров) |
| 2026-07-22T15:27:23Z | stage-4-quality:done | - |
