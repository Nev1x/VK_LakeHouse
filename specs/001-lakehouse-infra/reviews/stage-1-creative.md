# Stage 1 — Creative Team, консолидированный отчёт (001-lakehouse-infra)

Дата: 2026-07-19. Состав: Brainstormer, Critical Analyst, System Analyst, Hard Critic
(4 параллельных субагента). Директор: Creative Director (основная сессия).

## Ключевые решения, вошедшие в spec.md

1. **Каталог Iceberg — JDBC на Postgres** (Brainstormer, альтернативы REST/Nessie и Hive
   Metastore отклонены: лишний сервис без пользы при одном движке; переоценка — при появлении
   второго движка, отдельным решением владельца).
2. **Bootstrap DDL и smoke — python-клиент `trino` + pytest**, не bash/CLI (Brainstormer +
   System Analyst): идемпотентность кодом; тот же io-адаптер переиспользует loader 002 (I-4);
   критично — контракт репо гоняет `pytest -q` перед каждым коммитом, без единого теста это
   exit 5 и красный гейт → pyproject.toml и pytest-smoke обязаны появиться уже в 001 (FR-011).
3. **Bucket'ы — гибрид** (Brainstormer): отдельный `raw` (immutable-зона loader'а, единственное
   исключение из I-4) + единый `warehouse` (Iceberg сам разносит bronze/silver/gold по
   namespace) + `ml-datasets` сразу (System Analyst: дешевле в 001, чем менять bootstrap в 006).
4. **Namespace-контракт решён в 001**: `iceberg.bronze|silver|gold`, smoke — в `iceberg.smoke`
   (System Analyst: ни один intent 002–004 этого не фиксировал — заложили бы разные допущения).
5. **Роль app_net зафиксирована** (Hard Critic, SIMPLIFY): граница приложений ↔ Trino;
   grafana ∈ public+app, trino ∈ app+data, minio/postgres ∈ data.
6. **Healthcheck = штатный liveness, функциональные проверки = smoke** (Hard Critic, SIMPLIFY —
   не дублировать smoke в healthcheck).
7. **Smoke ужесточён** (Hard Critic + Critical Analyst): round-trip с проверкой значений,
   cleanup, отдельный namespace, таймауты, циклы up→smoke→smoke и down→up→smoke.
8. **Ресурсы явно** (Hard Critic + Critical Analyst): jvm.config Trino под локальную машину,
   memory-лимиты compose, требования к Docker Desktop VM в architecture.md.
9. **Файловая структура** (System Analyst): compose/.env.example/Makefile/pyproject в корне,
   конфиги в `infra/`, код в `src/loftnav/`, smoke в `tests/smoke/` (не задевает
   `tests/agent-evals/`); новый `.gitignore` (в репо его нет — риск закоммитить .env).
10. **Секрет-скан учтён** (System Analyst): generic-паттерн «URL с userinfo» (логин и пароль
    внутри адреса до знака @) блокирует такие DSN → .env.example и iceberg.properties только
    с раздельными переменными; allowlist хука НЕ расширяем.

## Спорное решение → на гейт владельца

**Grafana в 001** (FR-014). Hard Critic: CUT в 005 (пустой контейнер три фичи подряд ≈
placeholder). Контраргумент: intent 001 обещает Grafana; топология/healthcheck/env фиксируются
один раз, 005 тогда только досыпает provisioning-файлы. Решение спеки: KEEP как осознанное
включение; финальное слово — владельца на approval-гейте stage-2.

## Отклонённые оспаривания Hard Critic

- «Три сети — cargo-cult» → KEEP: прямая механически проверяемая реализация I-1 (MUST),
  цена в compose нулевая, миграция с плоской сети позже — дороже.
- «Trino тяжеловесен, DuckDB проще» → вне мандата фичи: выбор движка зафиксирован уставом I-4;
  реальная проблема — enterprise-дефолты JVM — закрыта FR-012.
- «architecture.md дублирует intent» → KEEP: intent = план (замораживается), architecture.md =
  as-built (живёт и дописывается 002–006); формат — таблицы, пересказ прозой запрещён.

## Топ-риски Critical Analyst, вошедшие в требования

Пины версий и совместимость Trino↔JDBC-каталога (FR-001, Assumptions); гонки старта →
depends_on healthy + init-job completed (FR-007, FR-005); ловушки healthcheck'ов per-сервис
(FR-007); `down -v` против I-2 → штатные цели без `-v` + именованные volumes (FR-009, NFR-003);
память JVM/Docker VM (FR-012, NFR-002); конфликты портов → env-override + bind 127.0.0.1
(FR-003); BSD/macOS-совместимость Makefile (FR-009); идемпотентность bootstrap (FR-005) и
smoke (FR-010); .env-краевые случаи (FR-008, Edge Cases). Полный список 20 рисков и 13 пунктов
приёмки — в выводе агента (audit trail: событие agent:critical-analyst:done).

## Полные отчёты

Отчёты четырёх агентов консолидированы в этот файл и spec.md; сырые тексты — в transcript
прогона (события `agent:*` в `audit.md` дают тайминги и summary).
