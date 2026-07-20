# Pipeline Audit — append-only журнал (пишет только scripts/pipeline-state.sh)

| ts (UTC) | event | detail |
|---|---|---|
| 2026-07-20T07:13:52Z | init | scope=feature · Версионированный экспорт ML-датасета: CLI loftnav export-dataset из apartments_features в отдельный bucket MinIO, parquet/jsonl + манифест (snapshot, версия, схема), immutable версии, воспроизводимость |
| 2026-07-20T07:13:53Z | stage-1-creative:start | - |
| 2026-07-20T07:13:56Z | agent:creative-analyst:start | экспорт, манифест, версионирование, оспаривания |
| 2026-07-20T07:13:56Z | agent:system-analyst:start | контракты features as-built, s3-запись, манифест-схема |
| 2026-07-20T07:17:56Z | agent:system-analyst:done | export/ пакет, pyarrow единств. новая зависимость, S3Store расширить (bucket-параметр+list_objects+get_object, put_if_absent=immutable), snapshot-пин apartments_features FOR VERSION AS OF, общий pipeline-lock, ORDER BY id детерминизм, манифест+раскладка frozen по I-6, журнал stage='export' |
| 2026-07-20T07:19:22Z | agent:creative-analyst:done | 5 US, parquet+jsonl оба (jsonl нужен Decimal/datetime encoder), vNNN list+fail-loud коллизия, фото ТОЛЬКО ссылки (SSRF при копиях), детерминизм по СОДЕРЖИМОМУ не байтам parquet, манифест с target_populated:false/photo_handling:links + sha256, I-4 decision record для прямой записи в ml-datasets ОБЯЗАТЕЛЕН, 13 рисков, 7 YAGNI |
| 2026-07-20T07:21:11Z | confidence:stage-1-creative | level=green reason=spec-lint OK 10/10; развилки закрыты (parquet+jsonl, fail-loud vNNN, фото-ссылки, детерминизм по содержимому, I-4 decision record запланирован) |
| 2026-07-20T07:21:11Z | stage-1-creative:done | - |
| 2026-07-20T07:21:24Z | stage-2-audit:start | - |
| 2026-07-20T07:21:27Z | agent:tech-audit:start | аудит 006 |
| 2026-07-20T07:21:28Z | agent:constitution-gate:start | устав 006 (I-4 обход Trino, I-2 immutable) |
| 2026-07-20T07:27:27Z | agent:tech-audit:done | CRIT 1 (A1: I-4 единственное исключение — расширение до 2 требует уставного решения ИЛИ переформулировки 'ml-datasets вне периметра I-4'), WARN 9 (S3Store bucket allowlist, put_or_fail отдельный метод, TOCTOU=lock, ParquetWriter streaming P1/P2/C2, Decimal→str, list_objects CommonPrefixes+пагинация), INFO 8 |
| 2026-07-20T07:28:52Z | agent:constitution-gate:done | MUST-FLAG 0, SHOULD 0, NEEDS-INFO 0; I-4 PASS (ml-datasets — egress-зона вне каталога, симметрична raw, разделение из 001; обход не тихий I-13); рекомендация не-блокер: PATCH устава 1.0.0→1.0.1 уточнить формулировку 'единственное исключение' — решение владельца Часть III |
| 2026-07-20T07:30:46Z | constitution-gate | MUST-FLAG: 0 · SHOULD-FLAG: 0 · NEEDS-INFO: 0 |
| 2026-07-20T07:30:47Z | units-set | u1-s3-spike,u2-read-write,u3-run-cli,u4-tests-docs |
| 2026-07-20T07:30:49Z | user-approval | approved by Owner (delegated 2026-07-20) |
| 2026-07-20T07:30:50Z | confidence:stage-2-audit | level=green reason=spec-lint OK, plan-lint OK (20/20, 0 overreach), constitution 0/0/0 (I-4 PASS — egress-зона); approve по делегации; устав-PATCH вынесен владельцу отдельно |
| 2026-07-20T07:30:50Z | stage-2-audit:done | - |
| 2026-07-20T07:30:51Z | stage-3-dev:start | - |
| 2026-07-20T07:30:53Z | agent:kulibin:start | stage-3: pyarrow spike, S3Store, потоковый экспорт parquet+jsonl+манифест |
| 2026-07-20T07:54:41Z | unit-done | u1-s3-spike |
| 2026-07-20T07:54:43Z | unit-done | u2-read-write |
| 2026-07-20T07:54:45Z | unit-done | u3-run-cli |
| 2026-07-20T07:54:46Z | unit-done | u4-tests-docs |
| 2026-07-20T07:54:48Z | agent:kulibin:done | u1-u4 DONE; spike pyarrow 25.0.0 ParquetWriter streaming, MinIO CommonPrefixes+пагинация; 133 passed; parquet читается независимо 11=11; immutable put_or_fail fail-loud; allowlist S3Store; 0-HTTP; export 6с |
| 2026-07-20T07:54:49Z | confidence:stage-3-dev | level=green reason=сам прогнал: pytest 133 passed, ruff clean, smoke 4 passed, parquet читается независимо 11=row_count манифеста, target_populated=false/photo_handling=links; units 4/4 |
| 2026-07-20T07:54:49Z | stage-3-dev:done | - |
| 2026-07-20T07:55:05Z | stage-4-quality:start | checkpoint=37d978e997a6771ef19adf8b274e2ac529129f19 |
| 2026-07-20T07:55:09Z | agent:qa-verifier:start | адверсарная проверка 006 (финал) |
| 2026-07-20T08:04:33Z | agent:qa-verifier:done | PASS адверсарно: CRIT 0, WARN 1 (унаследованный lock-текст 'ingest уже идёт' вводит в заблуждение для export/transform/build-gold), INFO 1; immutability/независимое-чтение-3-оси/integrity-sha256/allowlist/0-HTTP/детерминизм/пустой-срез/конкурентность все PASS |
| 2026-07-20T08:04:34Z | stage-3-dev:invalidated | reset from stage-3-dev |
| 2026-07-20T08:04:34Z | stage-4-quality:invalidated | reset from stage-3-dev |
| 2026-07-20T08:04:34Z | stage-3-dev:start | - |
| 2026-07-20T08:06:34Z | unit-done | u1-s3-spike |
| 2026-07-20T08:06:36Z | unit-done | u2-read-write |
| 2026-07-20T08:06:38Z | unit-done | u3-run-cli |
| 2026-07-20T08:06:39Z | unit-done | u4-tests-docs |
| 2026-07-20T08:06:41Z | agent:kulibin:done | фикс WARNING: lock-текст 'ingest уже идёт'→'конвейер уже занят' (общий модуль для всех стадий); 133 passed |
| 2026-07-20T08:06:41Z | confidence:stage-3-dev | level=green reason=фикс lock-текста верифицирован: pytest 133 passed, ruff clean, тесты не завязаны на старый текст; units 4/4 |
| 2026-07-20T08:06:41Z | stage-3-dev:done | - |
