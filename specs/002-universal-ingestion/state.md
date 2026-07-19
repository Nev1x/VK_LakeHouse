# Pipeline State — Универсальный ingestion-загрузчик: CLI loftnav ingest, форматы CSV/Excel/JSON/JSONL, schema inference, raw в MinIO, bronze в Iceberg, quarantine, идемпотентность, журнал прогонов

- State-Version: 3
- SPEC_DIR: specs/002-universal-ingestion
- Scope: feature
- Ticket: —
- Started: 2026-07-19T22:09:05Z
- Updated: 2026-07-19T23:28:09Z
- Quality-HEAD: —

## Stages

- [x] stage-1-creative
- [x] stage-2-audit
- [x] stage-3-dev
- [-] stage-4-quality

## Gates

- constitution-gate: MUST-FLAG: 0 · SHOULD-FLAG: 0 · NEEDS-INFO: 0 (2026-07-19T22:24:03Z)
- user-approval: approved (2026-07-19T22:24:06Z, Owner (delegated 2026-07-20))
- quality-verdict: —

## Confidence

- confidence-stage-1-creative: green — spec-lint OK 10/10; 2 отчёта консолидированы; открытые вопросы закрыты явными решениями в FR (2026-07-19T22:15:12Z)
- confidence-stage-2-audit: green — spec-lint OK, plan-lint OK (21/21, 0 overreach), constitution 0/0/0 после правок; approve по делегации владельца (2026-07-19T22:24:07Z)
- confidence-stage-3-dev: green — фиксы верифицированы лично: pytest 44 passed, ruff clean, smoke 4 passed, ingest-demo идемпотентен; diff 12 файлов реализации (2026-07-19T23:28:01Z)
- confidence-stage-4-quality: —

> Файл ведёт `scripts/pipeline-state.sh` — чекбоксы, гейты и confidence руками не редактируются;
> журнал событий — `audit.md` рядом (append-only). Confidence — fail-safe сигнал стадий
> (spec 013): non-green блокирует следующий этап до `ack` владельца; green ничего не разблокирует;
> «—» = не задекларирован (поведение как до фичи).

## Units

- [x] unit:u1-io-core
- [x] unit:u2-readers-inference
- [x] unit:u3-write-path
- [x] unit:u4-cli-batch
- [x] unit:u5-tests-docs
