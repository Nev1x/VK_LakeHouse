# Pipeline State — Лофт-маркеры: additive-расширение silver.apartments_clean и gold.apartments_features колонками ceiling_height_m, wall_material, year_built (+ маппинги реального источника apartments); версия контрактов bump

- State-Version: 3
- SPEC_DIR: specs/007-loft-markers
- Scope: feature
- Ticket: —
- Started: 2026-07-22T14:18:16Z
- Updated: 2026-07-22T15:27:23Z
- Quality-HEAD: 8113d9fc6f6785235f6cea97dd16f87b77fc0735

## Stages

- [x] stage-1-creative
- [x] stage-2-audit
- [x] stage-3-dev
- [x] stage-4-quality

## Gates

- constitution-gate: MUST-FLAG: 0 · SHOULD-FLAG: 0 · NEEDS-INFO: 0 (2026-07-22T14:28:51Z)
- user-approval: approved (2026-07-22T14:28:55Z, Owner (delegated; инициатор фичи, выбор «Сделать сейчас» 2026-07-22))
- quality-verdict: PASS — matrix 13/13 DONE + багфикс медианы; pytest 144 passed целиком x2 + ruff clean + smoke 4 passed; адверсарно CRIT 0 WARN 0: ALTER из _SCHEMA, sanity-границы, медиана-детерминизм x5 с ручной сверкой, immutable v035 по sha; retry 0 (2026-07-22T15:27:18Z)

## Confidence

- confidence-stage-1-creative: green — spec-lint OK 10/10; компактный stage-1 (deviation в learnings), полный аудит на stage-2 (2026-07-22T14:19:34Z)
- confidence-stage-2-audit: green — spec-lint OK, plan-lint OK (9/9, 0 overreach), MUST-FLAG'и сняты дополнениями по формулировке гейта; approve по делегации (владелец — инициатор) (2026-07-22T14:28:56Z)
- confidence-stage-3-dev: green — сам прогнал: pytest 144 passed БЕЗ deselect, ruff clean, determinism x3 (тест+витрина), SELECT маркеров, features 26; units 4/4 (2026-07-22T15:14:25Z)
- confidence-stage-4-quality: green — вердикт PASS; сигналы прогнаны лично (pytest 144/ruff/determinism/SELECT маркеров) (2026-07-22T15:27:23Z)

> Файл ведёт `scripts/pipeline-state.sh` — чекбоксы, гейты и confidence руками не редактируются;
> журнал событий — `audit.md` рядом (append-only). Confidence — fail-safe сигнал стадий
> (spec 013): non-green блокирует следующий этап до `ack` владельца; green ничего не разблокирует;
> «—» = не задекларирован (поведение как до фичи).

## Units

- [x] unit:u1-alter-evolution
- [x] unit:u2-schema-fields
- [x] unit:u3-mappings-reprocess
- [x] unit:u4-tests-docs
