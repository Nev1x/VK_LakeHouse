# Pipeline State — Gold-витрины: агрегаты по районам/ценам/стилям для дашбордов + feature-таблица apartments_features для ML, инкрементальные пересчёты, frozen-схемы

- State-Version: 3
- SPEC_DIR: specs/004-gold-marts
- Scope: feature
- Ticket: —
- Started: 2026-07-20T01:02:56Z
- Updated: 2026-07-20T01:37:55Z
- Quality-HEAD: —

## Stages

- [x] stage-1-creative
- [x] stage-2-audit
- [x] stage-3-dev
- [ ] stage-4-quality

## Gates

- constitution-gate: MUST-FLAG: 0 · SHOULD-FLAG: 3 · NEEDS-INFO: 0 (2026-07-20T01:16:06Z)
- user-approval: approved (2026-07-20T01:16:10Z, Owner (delegated 2026-07-20))
- quality-verdict: —

## Confidence

- confidence-stage-1-creative: green — spec-lint OK 10/10; развилки закрыты (материализация, full rebuild, atomic swap, is_loft NULL); documented-gap лофт-маркеров (2026-07-20T01:09:32Z)
- confidence-stage-2-audit: green — spec-lint OK, plan-lint OK (19/19, 0 overreach), constitution MUST-FLAG 0 (SHOULD 3 в план); approve по делегации (2026-07-20T01:16:12Z)
- confidence-stage-3-dev: green — сам прогнал: pytest 98 passed, ruff clean, smoke 4 passed, 4 gold-таблицы, баланс 11=11, is_loft 0 non-null; units 4/4 (2026-07-20T01:37:55Z)
- confidence-stage-4-quality: —

> Файл ведёт `scripts/pipeline-state.sh` — чекбоксы, гейты и confidence руками не редактируются;
> журнал событий — `audit.md` рядом (append-only). Confidence — fail-safe сигнал стадий
> (spec 013): non-green блокирует следующий этап до `ack` владельца; green ничего не разблокирует;
> «—» = не задекларирован (поведение как до фичи).

## Units

- [x] unit:u1-spike-scaffold
- [x] unit:u2-marts
- [x] unit:u3-features-journal
- [x] unit:u4-cli-demo-docs
