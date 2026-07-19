# Plan 001 — lakehouse-infra

Вход: `spec.md` (после правок по аудиту stage-2). Отчёт аудита: `reviews/stage-2-audit.md`.

## Technical Approach

Docker Compose стек из 5 контейнеров (minio, postgres, trino, grafana + one-shot minio-init) на
трёх сетях; Iceberg-каталог `iceberg` = Trino Iceberg-коннектор → JDBC-каталог в Postgres →
warehouse в MinIO (native S3 filesystem). Bootstrap namespace'ов и smoke — Python
(клиент `trino`, pytest), единый io-паттерн для будущего loader'а 002. Все секреты — env;
Trino — file-based password auth (FR-015). Управление — Makefile (BSD-совместимый), as-built
документация — docs/architecture.md.

Ключевые технические решения (из аудита):

- **T1. Trino single-node** [FR-001, FR-012]: `config.properties` c
  `node-scheduler.include-coordinator=true` (без него single-node не исполняет запросы —
  CRITICAL C1 perf-аудита), `query.max-memory=1.5GB`, `query.max-memory-per-node=1.5GB`,
  `memory.heap-headroom-per-node=300MB`, `discovery.uri=http://localhost:8080`.
- **T2. Память** [FR-012, NFR-002]: jvm.config `-Xmx1792m -Xms1792m` (+G1GC,
  ExitOnOutOfMemoryError, HeapDumpOnOutOfMemoryError); compose mem_limit: trino 2816m (heap +
  ~1GB off-heap — CRITICAL C2: mem_limit==Xmx гарантирует OOM-kill), postgres 768m, minio
  1024m, grafana 512m, minio-init 128m. Сумма ≈5.1GB ≤ 6GB. CPU-лимиты намеренно не задаются
  (медленнее холодный JVM-старт без пользы). Абсолютные Xmx, не MaxRAMPercentage.
- **T3. S3-доступ** [FR-004]: native S3 (`fs.native-s3.enabled=true`), legacy hive-s3
  свойства не подмешивать (взаимоисключающие); `s3.path-style-access=true` (обязателен для
  MinIO), `s3.region=us-east-1` (фиктивный, требуется для SigV4), `s3.endpoint=http://minio:9000`.
- **T4. JDBC-каталог** [FR-004]: `iceberg.catalog.type=jdbc`,
  `iceberg.jdbc-catalog.{driver-class,connection-url,connection-user,connection-password,
  catalog-name,default-warehouse-dir=s3://warehouse/}`; драйвер Postgres бандлится в
  Trino-коннекторе (проверить в логах старта отсутствие ClassNotFoundException). Секреты —
  синтаксис `${ENV:VAR}` в properties; переменные обязаны попасть в контейнер через
  `environment:` (не только в host-.env). Имена свойств сверить с доками пиненного релиза
  (менялись между версиями — WARNING compat-аудита).
- **T5. Пины версий** [FR-001, NFR-006]: точные теги выбираются на первом шаге реализации
  сверкой с Docker Hub (модельные знания отстают ~6 мес): trinodb/trino (актуальный numbered
  release), postgres 16.x-alpine, minio/minio + minio/mc (RELEASE.-теги), grafana (актуальный
  стабильный мажор). Для каждого — `docker manifest inspect` на linux/arm64 (Apple Silicon без
  эмуляции). Python-пакеты: trino (0.3xx), pytest 8.x, ruff — зафиксировать точно в
  pyproject.toml на момент реализации.
- **T6. Trino auth** [FR-015]: `password-authenticator.name=file` + password.db (bcrypt, файл
  генерируется bootstrap-скриптом из `TRINO_USER/TRINO_PASSWORD` env, в git не попадает),
  `http-server.authentication.type=PASSWORD`,
  `http-server.authentication.allow-insecure-over-http=true` (loopback-MVP без TLS,
  задокументировано в architecture.md). Закрывает CRITICAL SEC-1 (blind CSRF → DROP).
- **T7. Порядок старта** [FR-005, FR-007]: postgres init создаёт БД `iceberg_catalog` через
  `POSTGRES_DB` (пользователь имеет права DDL — JdbcCatalog сам создаёт служебные таблицы);
  minio-init (`mc mb --ignore-existing`: raw, warehouse, ml-datasets) →
  `service_completed_successfully`; trino `depends_on` healthy(postgres, minio) + completed
  (minio-init); grafana ← healthy(trino). Healthchecks (liveness only): minio
  `/minio/health/ready` (5s/3s/5/10s), postgres `pg_isready -U $POSTGRES_USER -d $POSTGRES_DB`
  (5s/5s/5/15s), trino `curl -f localhost:8080/v1/info` (5s/5s/4/start_period 90s — холодный
  JVM), grafana `/api/health` (5s/3s/5/20s).
- **T8. Smoke** [FR-010]: pytest, python-клиент trino с BasicAuthentication; retry/backoff на
  первый запрос (ленивая инициализация каталога — healthy ≠ прогретый каталог); файловый lock
  через `os.open(O_CREAT|O_EXCL)` (не flock — BSD/macOS make); шаги: liveness всех сервисов →
  SHOW CATALOGS содержит iceberg → CREATE SCHEMA iceberg.smoke → CREATE TABLE → INSERT →
  SELECT → сравнение значений → DROP TABLE/SCHEMA. Отрицательный сценарий: отсутствующая env →
  понятная ошибка старта, не тихий литерал `${ENV:VAR}` как пароль (SEC-2).
- **T9. Логи** [NFR-004]: logging-driver json-file, max-size=10m, max-file=10 на каждый сервис;
  `make logs` = docker compose logs. Runbook OOM-диагностики в architecture.md
  (`docker inspect --format '{{.State.OOMKilled}}'`, exit 137, docker stats).
- **T10. Данные** [NFR-003]: только именованные volumes (pg_data, minio_data, grafana_data) —
  живут в VM, минуя VirtioFS; bind-mount — только для конфигов `infra/*` (read-only).
  Guardrail: ни один сервис без docker.sock, privileged, cap_add (SEC-4, F7).

## Units of Work

- **u1-compose-core** — docker-compose.yml (сервисы, сети, healthchecks, лимиты, логи),
  .env.example, .gitignore [FR-001, FR-002, FR-003, FR-007, FR-008, FR-012, NFR-002, NFR-003,
  NFR-004, NFR-005, NFR-006].
- **u2-trino-catalog** — infra/trino/{config.properties, jvm.config, catalog/iceberg.properties},
  password-auth bootstrap, infra/minio/bootstrap [FR-004, FR-005, FR-015, NFR-001].
- **u3-python-smoke** — pyproject.toml, src/loftnav/, bootstrap namespace'ов (bronze/silver/
  gold/quarantine), tests/smoke/test_stack_up.py [FR-006, FR-010, FR-011].
- **u4-make-docs** — Makefile (up/down/smoke/ps/logs, BSD-совместимый, проверка .env),
  docs/architecture.md, заготовки infra/grafana/provisioning [FR-009, FR-013, FR-014, NFR-001].

## Implementation Steps

1. **Пины** (T5): сверить теги на Docker Hub + arm64-манифесты; свериться с доками Trino
   пиненного релиза по именам свойств iceberg.jdbc-catalog.* / fs.native-s3 / password-auth.
   Результат шага — таблица версий, уходит в architecture.md. [NFR-006]
2. **u1-compose-core** (T1, T2, T7, T9, T10): compose + .env.example + .gitignore; проверка
   `docker compose config` (порты только 127.0.0.1 из перечня FR-003, нет :latest, нет
   plaintext-кредов).
3. **u2-trino-catalog** (T3, T4, T6): конфиги Trino + auth + minio-init; `make up` до зелёных
   healthchecks; проверка логов Trino (каталог поднялся, драйвер найден, env-подстановка
   сработала).
4. **u3-python-smoke** (T8): pyproject + скелет + bootstrap namespace'ов + pytest-smoke;
   `pytest -q && ruff check .` зелёные; негативный сценарий env.
5. **u4-make-docs**: Makefile-цели (вкл. проверку наличия .env и читаемую ошибку без Docker
   daemon), architecture.md as-built (таблицы: версии, сети/членство, host+internal порты,
   bucket'ы/namespace'ы вкл. quarantine, env-контракт, лимиты, OOM-runbook, down -v warning,
   заметки о будущем loader и I-4-дисциплине). [FR-013]
6. **Приёмка** (Success Criteria спеки): чистый старт → smoke → smoke повторно →
   down → up → smoke; замер фактического времени тёплого старта и smoke (NFR-001) — числа в
   architecture.md; `docker compose config`-проверки; secret-скан хука зелёный.

Каждый unit завершается своим convergence-check (`unit-done`) до stage-3 done.

## Files to Create/Modify

Создаются: `docker-compose.yml`, `.env.example`, `.gitignore`, `Makefile`, `pyproject.toml`,
`src/loftnav/__init__.py`, `infra/trino/config.properties`, `infra/trino/jvm.config`,
`infra/trino/catalog/iceberg.properties`, `infra/minio/bootstrap.sh`,
`infra/grafana/provisioning/{datasources,dashboards}/.gitkeep`,
`src/loftnav/bootstrap.py` (идемпотентный bootstrap namespace'ов через Trino),
`tests/smoke/test_stack_up.py`, `tests/smoke/conftest.py`, `docs/architecture.md`.
Модифицируются: — (харнес-файлы не затрагиваются; tests/agent-evals не трогается).

## Known Risks

1. **Пины по памяти модели устарели** (compat WARN×3) → шаг 1 плана: сверка с Docker Hub/доками
   до написания конфигов; финальная истина — живой smoke (I-13).
2. **NFR-001 (120с тёплый старт) не подтверждён эмпирически** (perf W1) → замер на машине
   владельца в шаге 6; при провале — тюнинг start_period/ресурсов, числа в architecture.md.
3. **8GB VM — впритык** (perf W6) → минимум зафиксирован честно, рекомендация 10GB в
   architecture.md.
4. **allow-insecure-over-http** (T6) — компромисс loopback-MVP: пароль ходит по HTTP в пределах
   127.0.0.1/compose-сетей; TLS — вне scope 001, задокументировано.
5. **Общие root-креды MinIO для Trino и будущего loader'а** (arch F7) — осознанный MVP-риск в
   Authentication & Access спеки; least-privilege политики — кандидат в отдельную фичу.
6. **Grafana пустая до 005** (FR-014) — осознанное включение, владелец может Revise.
7. **env-подстановка ${ENV:VAR}** — при опечатке синтаксиса возможен тихий литерал вместо
   пароля (SEC-2) → негативный тест в smoke (T8).
8. **Первый запрос после healthy медленный** (ленивый каталог, perf W2) → retry/backoff в
   smoke, отдельный таймаут первого запроса.

## Traceability

FR-001→T1/T5/шаг2 · FR-002→шаг2 · FR-003→шаг2/6 · FR-004→T3/T4/шаг3 · FR-005→T7/шаг3 ·
FR-006→u3/шаг4 · FR-007→T7/шаг2 · FR-008→шаг2 · FR-009→u4/шаг5 · FR-010→T8/шаг4 ·
FR-011→u3/шаг4 · FR-012→T1/T2/шаг2 · FR-013→u4/шаг5 · FR-014→u4/шаг5 · FR-015→T6/шаг3 ·
NFR-001→T7/шаг6 · NFR-002→T2 · NFR-003→T10 · NFR-004→T9 · NFR-005→шаг2/6 · NFR-006→T5/шаг1.
