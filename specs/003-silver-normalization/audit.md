# Pipeline Audit — append-only журнал (пишет только scripts/pipeline-state.sh)

| ts (UTC) | event | detail |
|---|---|---|
| 2026-07-19T23:29:52Z | init | scope=feature · Silver-нормализация: единая схема apartments_clean, декларативный маппинг-конфиг per-источник, приведение типов/единиц, дедупликация, инкрементальность, quarantine, CLI loftnav transform |
| 2026-07-19T23:29:53Z | stage-1-creative:start | - |
| 2026-07-19T23:29:56Z | agent:creative-analyst:start | stories+альтернативы+риски+оспаривания |
| 2026-07-19T23:29:56Z | agent:system-analyst:start | контракты 002 as-built, схема silver, инкрементальность |
| 2026-07-19T23:34:27Z | agent:system-analyst:done | transform/ пакет, TOML+tomllib (0 новых deps), инкрементальность anti-join по журналу, reprocess по хэшу конфига, DECIMAL для денег/площади, рефакторинги: ident.py + общий chunked_insert + last_status c фильтром stage; apartments_clean объявить frozen |
| 2026-07-19T23:36:48Z | agent:creative-analyst:done | 5 US, MERGE+last-write-wins, YAML-vs-TOML развилка, 14 рисков, 7 CUT/SIMPLIFY |
| 2026-07-19T23:36:49Z | confidence:stage-1-creative | level=green reason=spec-lint OK 10/10; развилки аналитиков закрыты решениями в FR (TOML, MERGE, DECIMAL, explicit reprocess) |
| 2026-07-19T23:36:49Z | stage-1-creative:done | - |
| 2026-07-19T23:36:55Z | stage-2-audit:start | - |
| 2026-07-19T23:36:58Z | agent:tech-audit:start | объединённый аудит спеки 003 |
| 2026-07-19T23:36:59Z | agent:constitution-gate:start | сверка 003 с уставом |
| 2026-07-19T23:40:55Z | agent:constitution-gate:done | MUST-FLAG 0, SHOULD 0, NEEDS-INFO 0 с первого прогона; I-2 разобран по существу: MERGE-upsert и явный reprocess легитимны как продолжение прецедента 002 |
| 2026-07-19T23:46:53Z | agent:tech-audit:done | CRIT 1 (call-site last_status в ingest/run.py:264 при рефакторинге stage-фильтра), WARN 8 (ReDoS-cap, enum_map=dict, MERGE partition-предикат, fetchmany, порядок рефакторинг-затем-код, Decimal без float, fallback-атомарность), INFO 11 (Decimal bind подтверждён, DDL ARRAY-синтаксис, tomllib rb) |
| 2026-07-19T23:47:57Z | constitution-gate | MUST-FLAG: 0 · SHOULD-FLAG: 0 · NEEDS-INFO: 0 |
| 2026-07-19T23:47:59Z | units-set | u1-refactors,u2-mapping-normalize,u3-silver-write,u4-cli-demo-docs |
| 2026-07-19T23:48:01Z | user-approval | approved by Owner (delegated 2026-07-20) |
| 2026-07-19T23:48:02Z | confidence:stage-2-audit | level=green reason=spec-lint OK, plan-lint OK (21/21, 0 overreach), constitution 0/0/0 первым прогоном; approve по делегации |
| 2026-07-19T23:48:02Z | stage-2-audit:done | - |
| 2026-07-19T23:48:04Z | stage-3-dev:start | - |
| 2026-07-19T23:48:06Z | agent:kulibin:start | stage-3: u1-рефакторинги с регрессией 002, spike MERGE, реализация transform |
| 2026-07-20T00:29:47Z | unit-done | u1-refactors |
| 2026-07-20T00:29:49Z | unit-done | u2-mapping-normalize |
| 2026-07-20T00:29:51Z | unit-done | u3-silver-write |
| 2026-07-20T00:29:52Z | unit-done | u4-cli-demo-docs |
| 2026-07-20T00:29:54Z | agent:kulibin:done | u1-u4 DONE после восстановления с обрыва (состояние перепроверено по факту); spike MERGE успешен; 74 passed; transform-demo 17с, инкремент 7с; дефект partial-повтора найден и закрыт |
| 2026-07-20T00:29:55Z | confidence:stage-3-dev | level=green reason=сам прогнал: pytest 74 passed, ruff clean, smoke 4 passed, SELECT silver 6/6 distinct с Decimal, reprocess-протокол и чистый transform подтверждены; units 4/4 |
| 2026-07-20T00:29:55Z | stage-3-dev:done | - |
