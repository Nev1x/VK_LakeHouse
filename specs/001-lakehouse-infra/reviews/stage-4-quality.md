# Stage 4 — Quality Team, отчёт (001-lakehouse-infra)

Дата: 2026-07-20. Состав: Requirements Validator, Test Engineer, Code Reviewer, Technical
Writer (4 параллельных субагента) + fix-цикл + повторная верификация. QA Director — основная
сессия.

## Проход 1 → FAIL (retry 1)

- Requirements Validator: 27/27 DONE (матрица — requirements-matrix.md).
- Test Engineer: 5/6 PASS, **1 FAIL** — smoke валился при остановленной Grafana (нарушение
  I-8: liveness включал Grafana блокирующе). Auth-проверки FR-015: 401 без кредов, 200 с
  кредами, plain-HTTP на 8080 отвергается (TLS-only) — PASS. Порты/пины/секреты — PASS.
- Code Reviewer: CRIT 0, WARN 1 (stale docstring trino_client «HTTP» при факте HTTPS — I-14),
  INFO 5; T1–T10 плана применены полностью, 4 CRITICAL аудита stage-2 закрыты в коде.
- Technical Writer: CRIT 0, WARN 3 (docstring; нет quickstart; нет TLS-note), INFO 4;
  architecture.md построчно совпадает с фактом; +3 кандидата в pipeline-rules (переданы
  владельцу).

## Fix-цикл (возврат в stage-3, narrow scope, kulibin)

1. smoke разделён: `test_data_plane_liveness` (MinIO/Trino — блокирующие) +
   `test_grafana_liveness_non_blocking` (warning при недоступности, suite зелёный) — I-8.
2. docstring trino_client приведён к факту (HTTPS:8443/self-signed/verify=False).
3. architecture.md: quickstart с нуля, self-signed TLS предупреждение, дата замеров +
   «переизмерить при изменении состава», minio-init/ps -a note.
Checkpoint: fix-коммит на feature/001-lakehouse-infra, дерево чистое.

## Проход 2 → верификация фиксов (лично QA Director, свежие прогоны)

- Негативный сценарий I-8: `docker stop loftnav-grafana` → `make smoke` → **4 passed,
  1 warning** (зелёный) → `docker start` → healthy. ✔
- `pytest -q` → 4 passed; `ruff check .` → All checks passed. ✔
- Diff fix-цикла — ровно 3 ожидаемых файла (test_stack_up.py, trino_client.py,
  architecture.md), харнес не тронут. ✔
- Остальные оси прохода 1 (auth 401/200/TLS-only, compose config порты/пины/секреты,
  идемпотентность smoke, персистентность volumes) фиксом не затронуты — их evidence остаётся
  валидным (изменялись только smoke-тест, docstring и docs).

## Вердикт: **PASS**

Основание: requirements-matrix 27/27 DONE; тесты зелёные (pytest 4 passed, ruff clean, smoke
идемпотентен, негативный сценарий I-8 зелёный); CRITICAL по всем ревьюерам = 0 после
fix-цикла; сборка = поднятый стек 4/4 healthy; все 4 CRITICAL аудита stage-2 закрыты в коде;
секрет-скан зелёный. Retry счётчик: 1 из 2.

## Хвосты → бэклог (не блокируют 001)

1. Ужесточение внутреннего беспарольного HTTP:8080 Trino (compose-сети) — кандидат-фича.
2. Least-privilege креды MinIO (loader→raw, trino→warehouse) — кандидат-фича.
3. 3 кандидата в docs/pipeline-rules.md (Tech Writer) — решение владельца.
