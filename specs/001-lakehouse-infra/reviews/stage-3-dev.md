# Stage 3 — Dev Team, отчёт (001-lakehouse-infra)

Дата: 2026-07-19/20. Исполнитель: kulibin (канонический автономный dev), Tech Lead — основная
сессия (инвентарь агентов: kulibin/renata/semiglazka/pushkin; кодит kulibin, новых агентов не
нанимали — решение владельца «использовать агентов по назначению»).

## Результат

Все 4 units DONE, стек работает. Пины: trino:483, postgres:16.14-alpine3.23,
minio RELEASE.2025-09-07, mc RELEASE.2025-08-13, grafana:12.3.8; python: trino 0.338.0,
pytest 9.1.1, ruff 0.15.22, bcrypt 5.0.0 (venv, Python 3.12/uv).

## Решения и trade-offs (отклонения от плана, эмпирика I-13)

1. **Trino auth: HTTPS dual-port вместо HTTP+allow-insecure** (план T6/исходный FR-015).
   Trino by design отклоняет пароль по HTTP; флаг разрешает только беспарольный insecure.
   Реализовано: internal HTTP:8080 (не публикуется) + публикуемый HTTPS:8443 (self-signed,
   host 127.0.0.1:8080→8443). FR-015 спеки уточнён пометкой stage-3. Trade-off: внутренний
   HTTP беспарольный в пределах compose-сетей (MVP-риск, задокументирован).
2. **internal-communication.shared-secret** обязателен при auth даже single-node — env
   `TRINO_INTERNAL_SECRET`.
3. **Служебные таблицы JDBC-каталога** (Iceberg 1.11: init-catalog-tables недоступен из Trino)
   — пред-создание V0 DDL в `infra/postgres/init/01-iceberg-catalog.sql`, Trino идемпотентно
   мигрирует до V1. Проверено на рестарте.
4. **query.max-memory-per-node 1.5→1.4GB** — валидатор Trino: per-node + headroom ≤ heap.
5. pytest 9.x вместо 8.x из плана (актуальная, совместима).

## Верификация (двойная: kulibin + независимо Tech Lead)

- `docker compose ps`: 4/4 loftnav-* healthy; порты ровно 127.0.0.1:{3000,9000,9001,8080→8443};
  postgres без host-bind. ✔ оба
- `docker compose config`: published только {3000,8080,9000,9001}; `:latest` 0; userinfo-URL 0;
  `.env`/`.venv`/`infra/trino/auth` gitignored. ✔ оба
- smoke: 3 passed — трижды у kulibin (включая цикл down→up→smoke и персистентность реальной
  Iceberg-строки через рестарт) + независимый прогон Tech Lead (3 passed, 7s). ✔
- Контракт `pytest -q && ruff check .`: 3 passed / All checks passed. ✔ оба
- Замеры NFR-001: тёплый up→healthy 34–50с (лимит 120с), smoke 1.4–7с (лимит 90с) — в
  architecture.md §11.
- Харнес не тронут; git-коммитов нет (по указанию Tech Lead — коммиты после Stage 4).

## Хвосты (переданы в Stage 4 / бэклог)

- Внутренний HTTP:8080 Trino беспарольный (compose-сети) — кандидат на ужесточение.
- Общие root-креды MinIO (MVP-риск из спеки, least-privilege отложен).
- Гонка «healthy ≠ auth готов» закрыта retry в bootstrap/smoke (ожидаемое поведение).
