# Spec 001 — lakehouse-infra (базовая инфраструктура LakeHouse «ЛофтНавигатор»)

Статус: stage-1 draft → на аудит stage-2. Scope: feature. Intent: `specs/001-lakehouse-infra/intent.md`.

## Overview

Первая фича платформы LoftNavigator: воспроизводимый локальный LakeHouse-стек на Docker Compose —
MinIO (объектное хранилище), PostgreSQL (JDBC-каталог Iceberg), Trino (SQL-движок,
Iceberg-коннектор), Grafana (UI-обвязка под фичу 005). Итог: `make up` поднимает стек с нуля до
зелёных healthchecks, `make smoke` доказывает работоспособность цепочки Trino → Iceberg → MinIO
реальным round-trip'ом данных, все контракты (сети, каталог, namespace'ы, bucket'ы, env-имена)
зафиксированы для фич 002–006.

**WHY:** все последующие фичи (ingestion 002, silver 003, gold 004, дашборды 005, ML-экспорт 006)
строятся на этих контрактах; менять их задним числом — дорого (I-6).

## User Stories

- **US-1. Холодный старт.** Как владелец платформы, я хочу командой `make up` поднять весь стек
  с нуля на чистой машине без ручных шагов. _Приёмка:_ все контейнеры `loftnav-*` зелёные по
  healthcheck (I-10), включая первый запуск с pull образов.
- **US-2. Доказанная готовность.** Как владелец, я хочу `make smoke`, который доказывает — не
  «контейнеры запущены», а «Trino реально создаёт/пишет/читает Iceberg-таблицу в MinIO через
  JDBC-каталог» (I-13). _Приёмка:_ round-trip с проверкой значений, cleanup за собой.
- **US-3. Секреты вне git.** Как владелец, я хочу, чтобы все креды жили только в `.env` (вне git),
  а репо содержал лишь `.env.example` с нефункциональными плейсхолдерами (I-7). _Приёмка:_
  secret-скан зелёный, в compose нет plaintext-кредов и дефолтов admin/admin.
- **US-4. Готовые контракты для 002–006.** Как команда следующих фич, мы хотим зафиксированные
  имена сетей, каталога, namespace'ов, bucket'ов, env-переменных и make-целей, чтобы подключаться
  к готовой структуре. _Приёмка:_ контракты записаны в `docs/architecture.md` (as-built).
- **US-5. Понятная диагностика.** Как владелец, я хочу видеть статус каждого сервиса и получать
  читаемую ошибку (не зависание) при недоступности Trino/каталога (I-8, I-9). _Приёмка:_
  healthchecks у всех сервисов; smoke фейлится с внятным сообщением и таймаутом.

## Functional Requirements

- **FR-001 Compose-стек.** `docker-compose.yml` в корне репо: сервисы minio, postgres, trino,
  grafana + one-shot init-контейнер `minio-init`. Все образы запинены точными тегами
  (`:latest` запрещён); все сервисы имеют `container_name` с префиксом `loftnav-`.
- **FR-002 Сети.** Три сети: `public_net` (Grafana ↔ host), `app_net` (граница приложений:
  Grafana ↔ Trino; сюда же встанут будущие app-сервисы), `data_net` (Trino ↔ MinIO ↔ Postgres;
  наружу не публикуется — I-1). Размещение: grafana ∈ public+app; trino ∈ app+data;
  minio, postgres, minio-init ∈ data.
- **FR-003 Порты.** Публикация только на `127.0.0.1`, host-порты переопределяемы через `.env`:
  Grafana `3000`, Trino `8080` (host-доступ: smoke, будущие CLI 002 / отладка; защищён паролем —
  FR-015), MinIO S3 `9000` (нужен loader'у 002 для raw; доступ по кредам MinIO), MinIO Console
  `9001` (browser-QA; решение владельца уже зафиксировано в team.params/BROWSER_WORKFLOW).
  PostgreSQL наружу НЕ публикуется (нужен только Trino внутри data_net). Перечень 3000/8080/
  9000/9001 — исчерпывающий список entrypoints по I-1; ратифицируется владельцем на
  approval-гейте этой спеки (Approve = решение владельца, фиксируется в state.md).
- **FR-004 Каталог Iceberg.** Trino-каталог с именем `iceberg`: JDBC-каталог → Postgres
  (отдельная БД `iceberg_catalog`, пользователь с правами DDL), warehouse → MinIO bucket
  `warehouse`. Конфиг — `infra/trino/catalog/iceberg.properties`, креды через env-подстановку,
  connection-url БЕЗ userinfo (`user:pass@` запрещён secret-сканом).
- **FR-005 Bucket'ы и bootstrap.** `minio-init` идемпотентно (`mc mb --ignore-existing`) создаёт
  bucket'ы: `raw` (immutable-зона исходных файлов, владелец — будущий loader), `warehouse`
  (managed-данные Iceberg: bronze/silver/gold), `ml-datasets` (под фичу 006, пустой). Trino и
  smoke стартуют после успешного завершения init (`service_completed_successfully`).
- **FR-006 Namespace'ы слоёв и quarantine-контракт.** Bootstrap-скрипт (python, клиент `trino`)
  идемпотентно создаёт схемы `iceberg.bronze`, `iceberg.silver`, `iceberg.gold` и
  `iceberg.quarantine` (единый namespace отбраковки для всех слоёв: таблицы вида
  `<слой>_<источник>_rejects` с колонками причины и слоя-источника; реализация таблиц — 002/003,
  здесь резервируется ИМЯ контракта, чтобы 002 и 003 не изобрели разные конвенции; quarantine —
  Iceberg-таблицы, а не файлы, чтобы Grafana 005 могла показывать метрики отбраковки через Trino
  без нарушения I-4). Слой raw — НЕ Iceberg (файлы как есть в bucket `raw`). Smoke использует
  отдельный namespace `iceberg.smoke`, не medallion-слои.
- **FR-007 Healthchecks.** У каждого сервиса — штатный liveness: MinIO `/minio/health/ready`,
  Postgres `pg_isready -U $POSTGRES_USER -d $POSTGRES_DB`, Trino `/v1/info`, Grafana
  `/api/health`; `start_period` с запасом под холодный старт JVM. Функциональные проверки
  каталога — зона smoke, НЕ healthcheck (не дублировать). Порядок старта: `depends_on:
  condition: service_healthy` (trino ← postgres, minio; grafana ← trino) + `minio-init`
  по `service_completed_successfully`.
- **FR-008 Секреты.** `.env.example` — только раздельные переменные (без DSN с userinfo), значения
  — нефункциональные плейсхолдеры `changeme_local_dev`; `.gitignore` (новый) исключает `.env*`
  (с явным `!.env.example`), `docker-compose.override.yml`, `__pycache__/`, `.venv/`,
  `.pytest_cache/`, `.ruff_cache/`. `make up` без `.env` падает с понятным сообщением
  «скопируй .env.example → .env», а не поднимает стек с пустыми кредами.
- **FR-009 Make-цели.** `make up` (compose pull с прогрессом → up -d → ожидание healthy),
  `make down` (БЕЗ `-v`; удаление volumes — только явной осознанной командой вне штатных целей,
  I-2), `make smoke` (= `pytest -q tests/smoke`), `make ps`/`make logs` (диагностика). Makefile
  совместим с macOS/BSD-утилитами (без GNU-специфики), протестирован на машине владельца.
- **FR-010 Smoke-тест.** `tests/smoke/test_stack_up.py` (pytest + python-клиент `trino`):
  (1) healthchecks сервисов отвечают; (2) `SHOW CATALOGS` содержит `iceberg`; (3) в
  `iceberg.smoke` создаётся таблица, пишутся строки, читаются обратно и **сравниваются
  значения** (round-trip, не «запрос не упал»); (4) cleanup — таблица и schema `smoke`
  удаляются; (5) при недоступности сервиса — понятная ошибка с таймаутом, не зависание.
  Повторный прогон и цикл down→up→smoke проходят (идемпотентность, персистентность volumes).
- **FR-011 Python-скелет.** `pyproject.toml` ([project] `loftnav`, `src/`-layout,
  `[tool.pytest.ini_options]` c `testpaths = ["tests"]`, `[tool.ruff]` c `extend-exclude`
  каталогов харнеса — scripts/, Product_agents/, coordination/, .githooks/) +
  `src/loftnav/__init__.py`. Обязателен уже в 001: контракт репо гоняет
  `pytest -q && ruff check .` перед каждым коммитом — без единого теста pytest выходит с кодом 5
  и гейт красный. Smoke на pytest закрывает это без заглушек (I-11). Явные testpaths/exclude
  защищают гейт от будущих python-файлов харнеса.
- **FR-012 Ресурсы.** Явный `jvm.config` Trino (heap под локальную машину, а не
  enterprise-дефолт) + memory-лимиты в compose на все сервисы; минимальные требования к Docker
  Desktop VM задокументированы в `docs/architecture.md`.
- **FR-013 as-built документация.** `docs/architecture.md`: фактическая схема (сервисы, версии
  образов, сети и членство, порты host-loopback И internal-DNS контракт (`trino:8080`,
  `minio:9000`, `postgres:5432` внутри compose-сетей — для datasource 005 и будущих
  контейнеров), bucket'ы, namespace'ы (вкл. quarantine), env-контракт, make-цели, требования к
  ресурсам, runbook диагностики OOM, предупреждение о `down -v`, заметка о будущей
  контейнеризации loader'а (dual-membership app_net+data_net) и о том, что I-4 layer-discipline
  обеспечивается кодом/ревью, а не ACL Trino. Формат — таблицы/схема as-built, не пересказ
  intent. Фичи 002–006 дописывают свои разделы, не переписывая этот.
- **FR-014 Grafana в 001 — осознанное включение (решено).** Grafana входит в 001 контейнером с
  healthcheck, admin-кредами из env и заготовленными каталогами provisioning
  (`infra/grafana/provisioning/{datasources,dashboards}/`), БЕЗ datasource и дашбордов (их
  привозит 005 — см. intent 005). Решение спеки: KEEP — топология/healthcheck/env-контракт
  фиксируются один раз, 005 только добавляет provisioning-файлы, не трогая compose; это честная
  частичная инфраструктура со ссылкой на фичу-продолжение, не placeholder (I-11). Альтернатива
  Hard Critic (вынести целиком в 005) зафиксирована в stage-1 отчёте; владелец может переиграть
  через Revise на approval-гейте.
- **FR-015 Аутентификация Trino.** Trino поднимается с password-аутентификацией (file-based
  password authenticator: пользователь `loftnav`, пароль из env `TRINO_PASSWORD`, bcrypt-хэш
  генерируется при bootstrap). _Уточнение stage-3 (эмпирика):_ Trino по дизайну запрещает
  password-auth по небезопасному HTTP (`allow-insecure-over-http` разрешает лишь беспарольный
  доступ) → dual-port: внутренний HTTP:8080 (discovery/health/internal, НЕ публикуется) +
  HTTPS:8443 с self-signed keystore — единственный публикуемый порт Trino
  (host `127.0.0.1:8080` → container `8443`, перечень FR-003 не меняется). Закрывает вектор
  blind-CSRF со сторонней страницы в браузере владельца (`/v1/statement` принимал бы POST без
  auth) и приводит публикацию Trino-порта в соответствие I-7 («админ-консоли не публикуются
  без пароля»). Smoke и будущие клиенты (002, Grafana 005) ходят на `trino:8443` (https,
  self-signed) с кредами из env; внутренний беспарольный HTTP:8080 ограничен compose-сетями —
  осознанный MVP-риск, кандидат на ужесточение отдельной фичей.

## Non-Functional Requirements

- **NFR-001 Производительность старта.** Тёплый `make up` (образы уже спуллены) → все healthy
  ≤ 120 с; `make smoke` целиком ≤ 90 с; каждая сетевая проверка smoke с таймаутом ≤ 30 с.
- **NFR-002 Ресурсы.** Суммарный memory-limit стека ≤ 6 GB (Trino heap ≤ 2 GB); стек работает
  при Docker Desktop VM с 8 GB. Требования записаны в architecture.md.
- **NFR-003 Надёжность/персистентность.** Именованные volumes для Postgres и MinIO; цикл
  `make down && make up` сохраняет каталог и данные (проверяется в приёмке); штатные цели
  никогда не удаляют volumes (I-2).
- **NFR-004 Наблюдаемость.** Healthcheck у 100% сервисов; `make ps` показывает статусы; smoke
  при провале печатает, какой именно шаг цепочки Trino→каталог→MinIO упал (I-9). Логи:
  logging-driver `json-file` с ротацией `max-size=10m`, `max-file=10` на каждый сервис — при
  демо-нагрузке это ≥ 7 дней истории (I-9 retention); настройка и способ чтения
  (`make logs` / `docker logs`) записаны в architecture.md.
- **NFR-005 Безопасность.** 0 секретов в git (secret-скан хука зелёный); 0 публикаций портов на
  `0.0.0.0`; 0 дефолтных кредов в compose (только env). Соответствие I-1/I-7 проверяемо по
  `docker compose config`.
- **NFR-006 Переносимость/сопровождаемость.** Все версии образов запинены; хостовые порты и
  креды переопределяемы через `.env` без правки compose; образы имеют arm64-варианты
  (Apple Silicon без эмуляции); `TZ` зафиксирован для сопоставимости логов.

## Authentication & Access

Корпоративного SSO нет (устав: SSO-слот удалён осознанно, v1.0.0). Модель доступа фичи:
платформа single-user, все опубликованные порты слушают только `127.0.0.1` локальной машины
владельца — сетевой периметр = машина (I-1). Доступы: Grafana — admin-логин/пароль из env
(`GRAFANA_ADMIN_USER/PASSWORD`, не admin/admin); MinIO Console — root-креды из env
(`MINIO_ROOT_USER/PASSWORD`); Trino — password-аутентификация (FR-015: пользователь `loftnav`,
пароль из env; каждая опубликованная консоль защищена паролем — I-7); PostgreSQL — доступен
только из `data_net` (наружу не публикуется), креды из env. Ролей продукта нет (TEST_ROLES="-").
Осознанный MVP-риск (зафиксирован): loader 002 и Trino используют общие root-креды MinIO —
least-privilege политики (loader → только bucket raw; Trino → только warehouse) отложены;
guardrail в плане: ни один сервис не получает docker.sock/privileged/лишних capabilities.

## Out of Scope

- Ingestion, загрузчики, любые данные квартир (002+); raw и ml-datasets bucket'ы создаются пустыми.
- Datasource и дашборды Grafana (005) — в 001 только контейнер и каталоги provisioning.
- Nginx/reverse-proxy, TLS, внешний доступ (нет внешних пользователей).
- Airflow/Dagster/оркестрация (решение владельца: CLI + Make).
- Trino-аутентификация/TLS между сервисами (single-user loopback MVP).
- Автоматический бэкап volumes (упоминание в runbook architecture.md — да; механизм — позже).

## Affected Services

Новые (кода платформы до 001 нет): compose-стек `loftnav-{minio,postgres,trino,grafana,minio-init}`,
`infra/` (конфиги trino/minio/grafana), `src/loftnav/` (python-скелет), `tests/smoke/`,
`Makefile`, `pyproject.toml`, `.gitignore`, `.env.example`, `docs/architecture.md`.
Харнес-файлы репо (scripts/, Product_agents/, .githooks/) не затрагиваются;
`tests/agent-evals/` не трогается (pytest его не подхватывает — там нет test_*.py).

## Edge Cases

- Запуск без `.env` / с неполным `.env` (новая переменная в example, старый .env) → явная ошибка,
  не полу-сконфигурированный стек.
- Повторный `make up` при живом стеке → no-op без пересоздания; повторный `make smoke` → зелёный
  (cleanup предыдущего прогона).
- `docker compose down -v` — вне штатных целей; предупреждение о необратимости в architecture.md.
- Занятый порт (5432/8080/3000/9000) на машине → переопределение через `.env`, понятная ошибка.
- Docker daemon не запущен → читаемая ошибка make, не стек-трейс compose.
- Медленный первый pull образов → отдельный шаг `pull` с прогрессом, healthcheck не «ложно падает».
- Apple Silicon: все образы arm64, без Rosetta-эмуляции.

## Rollback (откат, I-10)

Инфраструктурная фича без миграций данных: откат = `git checkout` предыдущей ревизии
compose/конфигов + `make up` (данные в именованных volumes не затрагиваются — NFR-003).
Частичный сбой `make up` (упавший minio-init, не стартовавший Trino) лечится идемпотентным
повторным `make up`; полное удаление фичи = `make down` (volumes сохраняются) + удаление файлов
фичи из git. Разрушающих операций, требующих бэкапа до отката, в 001 нет (bucket'ы/схемы
создаются пустыми, idempotent create-if-absent).

## Assumptions

- Машина владельца: macOS, Docker Desktop ≥ 8 GB VM (рекомендовано 10 GB), свободные
  loopback-порты по умолчанию 3000/8080/9000/9001 (переопределяемы).
- Точные версии образов выбирает stage-2/3 со сверкой по Docker Hub/докам пиненного релиза
  (знания моделей отстают: пин Trino, имена свойств iceberg.jdbc-catalog.*, native-s3 —
  верифицировать по докам и живому smoke); в спеке зафиксирован только запрет `:latest`.
- Демо-данных в 001 нет; smoke оперирует синтетической таблицей в `iceberg.smoke`.

## Success Criteria

1. Чистая машина: `cp .env.example .env` → `make up` → все `loftnav-*` healthy без ручных шагов.
2. `make smoke` зелёный; повторный прогон зелёный; `make down && make up && make smoke` зелёный
   (данные и каталог пережили рестарт).
3. `docker compose config` подтверждает: опубликованы ТОЛЬКО порты из перечня FR-003 и только
   bind'ами на 127.0.0.1 (PostgreSQL не опубликован; публикаций на 0.0.0.0 нет), нет
   plaintext-кредов, нет `:latest`.
4. `pytest -q && ruff check .` зелёные из корня репо.
5. `docs/architecture.md` соответствует фактически развёрнутому (версии/сети/порты/контракты).
6. Secret-скан pre-commit зелёный на всём диффе фичи.
