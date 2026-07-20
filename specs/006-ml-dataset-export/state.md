# Pipeline State — Версионированный экспорт ML-датасета: CLI loftnav export-dataset из apartments_features в отдельный bucket MinIO, parquet/jsonl + манифест (snapshot, версия, схема), immutable версии, воспроизводимость

- State-Version: 3
- SPEC_DIR: specs/006-ml-dataset-export
- Scope: feature
- Ticket: —
- Started: 2026-07-20T07:13:52Z
- Updated: 2026-07-20T08:06:54Z
- Quality-HEAD: —

## Stages

- [x] stage-1-creative
- [x] stage-2-audit
- [x] stage-3-dev
- [-] stage-4-quality

## Gates

- constitution-gate: MUST-FLAG: 0 · SHOULD-FLAG: 0 · NEEDS-INFO: 0 (2026-07-20T07:30:46Z)
- user-approval: approved (2026-07-20T07:30:49Z, Owner (delegated 2026-07-20))
- quality-verdict: —

## Confidence

- confidence-stage-1-creative: green — spec-lint OK 10/10; развилки закрыты (parquet+jsonl, fail-loud vNNN, фото-ссылки, детерминизм по содержимому, I-4 decision record запланирован) (2026-07-20T07:21:11Z)
- confidence-stage-2-audit: green — spec-lint OK, plan-lint OK (20/20, 0 overreach), constitution 0/0/0 (I-4 PASS — egress-зона); approve по делегации; устав-PATCH вынесен владельцу отдельно (2026-07-20T07:30:50Z)
- confidence-stage-3-dev: green — фикс lock-текста верифицирован: pytest 133 passed, ruff clean, тесты не завязаны на старый текст; units 4/4 (2026-07-20T08:06:41Z)
- confidence-stage-4-quality: —

> Файл ведёт `scripts/pipeline-state.sh` — чекбоксы, гейты и confidence руками не редактируются;
> журнал событий — `audit.md` рядом (append-only). Confidence — fail-safe сигнал стадий
> (spec 013): non-green блокирует следующий этап до `ack` владельца; green ничего не разблокирует;
> «—» = не задекларирован (поведение как до фичи).

## Units

- [x] unit:u1-s3-spike
- [x] unit:u2-read-write
- [x] unit:u3-run-cli
- [x] unit:u4-tests-docs
