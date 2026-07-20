# Pipeline State — Gold-витрины: агрегаты по районам/ценам/стилям для дашбордов + feature-таблица apartments_features для ML, инкрементальные пересчёты, frozen-схемы

- State-Version: 3
- SPEC_DIR: specs/004-gold-marts
- Scope: feature
- Ticket: —
- Started: 2026-07-20T01:02:56Z
- Updated: 2026-07-20T01:49:23Z
- Quality-HEAD: 3a1f49ee1f355a49d9be45294c7f8fd786a30478

## Stages

- [x] stage-1-creative
- [x] stage-2-audit
- [x] stage-3-dev
- [x] stage-4-quality

## Gates

- constitution-gate: MUST-FLAG: 0 · SHOULD-FLAG: 3 · NEEDS-INFO: 0 (2026-07-20T01:16:06Z)
- user-approval: approved (2026-07-20T01:16:10Z, Owner (delegated 2026-07-20))
- quality-verdict: PASS — matrix 27/27 DONE; pytest 98 passed + ruff clean + smoke 4 passed; адверсарно CRIT 0 WARN 0: балансы 11=11, is_loft NULL, деление-на-ноль, атомарность swap, детерминизм; retry 0 (2026-07-20T01:49:19Z)

## Confidence

- confidence-stage-1-creative: green — spec-lint OK 10/10; развилки закрыты (материализация, full rebuild, atomic swap, is_loft NULL); documented-gap лофт-маркеров (2026-07-20T01:09:32Z)
- confidence-stage-2-audit: green — spec-lint OK, plan-lint OK (19/19, 0 overreach), constitution MUST-FLAG 0 (SHOULD 3 в план); approve по делегации (2026-07-20T01:16:12Z)
- confidence-stage-3-dev: green — сам прогнал: pytest 98 passed, ruff clean, smoke 4 passed, 4 gold-таблицы, баланс 11=11, is_loft 0 non-null; units 4/4 (2026-07-20T01:37:55Z)
- confidence-stage-4-quality: green — вердикт PASS с evidence; сигналы прогнаны лично (pytest/ruff/smoke/баланс/is_loft) (2026-07-20T01:49:23Z)

> Файл ведёт `scripts/pipeline-state.sh` — чекбоксы, гейты и confidence руками не редактируются;
> журнал событий — `audit.md` рядом (append-only). Confidence — fail-safe сигнал стадий
> (spec 013): non-green блокирует следующий этап до `ack` владельца; green ничего не разблокирует;
> «—» = не задекларирован (поведение как до фичи).

## Units

- [x] unit:u1-spike-scaffold
- [x] unit:u2-marts
- [x] unit:u3-features-journal
- [x] unit:u4-cli-demo-docs
