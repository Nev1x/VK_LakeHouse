# Архитектура платформы LoftNavigator — as-built

> Фактически развёрнутое состояние базовой инфраструктуры LakeHouse (фича `001-lakehouse-infra`).
> Формат — as-built (таблицы/схема того, что реально работает), НЕ пересказ intent.
> Фичи 002–006 **дописывают** свои разделы, не переписывая этот. Источник истины поведения —
> `docker-compose.yml`, `infra/`, `Makefile`, `pyproject.toml`. Устав: `docs/constitution.md`.

## 0. Quickstart: первый запуск с нуля

```sh
cp .env.example .env                       # 1. создать локальный .env (в git не попадает)
# 2. заполнить секреты в .env реальными значениями, например:
#    MINIO_ROOT_PASSWORD / POSTGRES_PASSWORD / TRINO_PASSWORD / TRINO_INTERNAL_SECRET /
#    TRINO_KEYSTORE_PASSWORD / GRAFANA_ADMIN_PASSWORD  →  openssl rand -hex 24
make up                                    # 3. поднять стек до healthy + bootstrap namespace'ов
make smoke                                 # 4. доказать round-trip Trino → Iceberg → MinIO
```

Требуется Docker Desktop (VM ≥ 8 GB) и `python3`+`uv` (либо `python3 -m venv`) для `.venv`.
`make up` без `.env` падает с понятным сообщением, а не поднимает стек с пустыми кредами.

> **Trino UI по HTTPS с self-signed сертификатом.** `https://127.0.0.1:8080` (и MinIO/Grafana по
> HTTP) — при открытии Trino в браузере будет предупреждение о недоверенном сертификате. Это
> **норма** для loopback-MVP (FR-015): сертификат self-signed, доверенный периметр = локальная
> машина. Клиенты (smoke, loader 002, Grafana 005) подключаются с `verify=False`.

## 1. Топология

Локальный стек Docker Compose (project `loftnav`), 5 контейнеров на трёх сетях:

```
            host loopback 127.0.0.1
   :3000        :8080(https)     :9000  :9001
     │              │              │      │
 ┌───────┐  public  │              │      │
 │grafana │──net─────┤              │      │
 └───┬────┘          │              │      │
     │ app_net       │              │      │
     └──────────► ┌──────┐          │      │
                  │trino │          │      │
                  └──┬───┘ data_net │      │
                     ├──────────► ┌─────────┐  ┌──────────┐
                     │            │  minio  │  │ postgres │
                     └──────────► └─────────┘  └──────────┘
                                   ▲  (minio-init: one-shot bootstrap bucket'ов)
```

Цепочка данных: `Trino (Iceberg-коннектор) → JDBC-каталог в PostgreSQL (метаданные) → warehouse в
MinIO (данные, native S3)`. Round-trip доказан `make smoke`.

`minio-init` — **one-shot** init-контейнер (создаёт bucket'ы и завершается): в обычном
`docker compose ps` его нет, он виден в `docker compose ps -a` со статусом `Exited (0)` — это норма,
а не сбой.

## 2. Версии образов (пины, `:latest` запрещён — FR-001/NFR-006)

| Сервис | Образ (пин) | Digest (наблюдаемый) |
|---|---|---|
| trino | `trinodb/trino:483` | `sha256:db58cc93e593a2706553745f276bb119c9810e69918be56ecde088ba7ccb0534` |
| postgres | `postgres:16.14-alpine3.23` | `sha256:42b8b8b29c8a4e933d88943e5b03001a78794905cf786e6e7634e9f2abd5a0d3` |
| minio | `minio/minio:RELEASE.2025-09-07T16-13-09Z` | `sha256:14cea493d9a34af32f524e538b8346cf79f3321eff8e708c1e2960462bd8936e` |
| minio (mc, init) | `minio/mc:RELEASE.2025-08-13T08-35-41Z` | `sha256:a7fe349ef4bd8521fb8497f55c6042871b2ae640607cf99d9bede5e9bdf11727` |
| grafana | `grafana/grafana:12.3.8` | `sha256:b1bfd4d07801edb308c2578a1161acfc75bc580501f5d80d866b1b9a3809d004` |

Все образы multi-arch (linux/amd64 + linux/arm64) — Apple Silicon без Rosetta-эмуляции (NFR-006).
Python-инструменты (pin в `pyproject.toml`): `trino==0.338.0`, `pytest==9.1.1`, `ruff==0.15.22`,
`bcrypt==5.0.0`. Java внутри Trino 483 — Temurin 25 (bundled).

## 3. Сети и членство (FR-002)

| Сеть | Назначение | Члены |
|---|---|---|
| `loftnav_public_net` | Grafana ↔ host (единственная наружу-смотрящая поверхность) | grafana |
| `loftnav_app_net` | граница приложений (Grafana ↔ Trino; сюда встанут app-сервисы 002+) | grafana, trino |
| `loftnav_data_net` | внутренняя data-сеть (наружу не публикуется, I-1) | trino, minio, postgres, minio-init |

## 4. Порты

### Host (публикуются ТОЛЬКО на 127.0.0.1 — I-1; исчерпывающий список FR-003)

| Host (127.0.0.1) | → контейнер | Сервис | Назначение |
|---|---|---|---|
| `3000` | grafana:3000 | Grafana | UI (пусто до 005) |
| `8080` | **trino:8443** | Trino | SQL/UI по **HTTPS** (password auth); smoke, CLI 002, отладка |
| `9000` | minio:9000 | MinIO S3 API | raw-доступ loader'а 002, S3-клиенты |
| `9001` | minio:9001 | MinIO Console | browser-QA |

PostgreSQL host-порт **не публикуется** (доступен только внутри `data_net`).

### Internal-DNS контракт (для datasource 005 и будущих контейнеров)

| Адрес | Протокол | Использование |
|---|---|---|
| `trino:8443` | HTTPS (self-signed) + password auth | **аутентифицированные клиенты** (Grafana 005, loader 002) — connect с verify=False |
| `trino:8080` | HTTP, passwordless (insecure) | только внутренний self-call координатора + healthcheck `/v1/info`; **не для приложений** |
| `minio:9000` | HTTP S3 | warehouse/raw доступ Trino и loader'а |
| `postgres:5432` | JDBC | JDBC-каталог Iceberg (Trino) |

## 5. Volumes (именованные — NFR-003; штатные цели НЕ удаляют)

| Volume | Монтируется | Данные |
|---|---|---|
| `loftnav_pg_data` | postgres:/var/lib/postgresql/data | метаданные JDBC-каталога Iceberg |
| `loftnav_minio_data` | minio:/data | bucket'ы (raw/warehouse/ml-datasets) |
| `loftnav_grafana_data` | grafana:/var/lib/grafana | стейт Grafana |

Конфиги `infra/*` монтируются bind-mount **read-only**. Персистентность проверена: цикл
`make down && make up` сохраняет каталог, namespace'ы и данные (write→restart→read round-trip).

## 6. Bucket'ы MinIO (FR-005, idempotent `mc mb --ignore-existing`)

| Bucket | Зона | Владелец |
|---|---|---|
| `raw` | immutable исходные файлы (I-2) | loader 002 |
| `warehouse` | managed Iceberg-данные bronze/silver/gold | Trino/Iceberg |
| `ml-datasets` | датасеты ML-экспорта (пусто) | фича 006 |

## 7. Namespace'ы каталога `iceberg` (FR-006)

| Namespace | Назначение |
|---|---|
| `iceberg.bronze` | типизированный append (002) |
| `iceberg.silver` | `apartments_clean` (003) |
| `iceberg.gold` | витрины + features (004) |
| `iceberg.quarantine` | **единый** namespace отбраковки всех слоёв: таблицы `<слой>_<источник>_rejects` (создают 002/003); Iceberg-таблицы, чтобы Grafana 005 показывала метрики отбраковки через Trino без нарушения I-4 |
| `iceberg.smoke` | только для `make smoke` (создаётся/удаляется каждый прогон) |

Слой `raw` — НЕ Iceberg (файлы как есть в bucket `raw`). Bootstrap namespace'ов идемпотентен
(`CREATE SCHEMA IF NOT EXISTS`), запускается автоматически из `make up`.

**I-4 layer-discipline** (raw→bronze→silver→gold, слой читает только предыдущий) обеспечивается
**кодом и ревью**, а НЕ ACL Trino — в single-user MVP у Trino один root-доступ к MinIO.

## 8. Env-контракт (`.env`, вне git; шаблон — `.env.example`, FR-008)

| Переменная | Назначение |
|---|---|
| `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` | root-креды MinIO (ими же ходит Trino и loader 002 — MVP-риск) |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` | владелец БД `iceberg_catalog`, JDBC-каталог |
| `POSTGRES_DB` | имя БД каталога (`iceberg_catalog`) |
| `TRINO_USER` / `TRINO_PASSWORD` | password-аутентификация Trino (bcrypt в `password.db`) |
| `TRINO_INTERNAL_SECRET` | `internal-communication.shared-secret` (обязателен при auth) |
| `TRINO_KEYSTORE_PASSWORD` | пароль self-signed keystore Trino HTTPS |
| `GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD` | admin Grafana (не admin/admin) |
| `GRAFANA_PORT` / `TRINO_PORT` / `MINIO_API_PORT` / `MINIO_CONSOLE_PORT` | переопределение host-портов |
| `TZ` | единый TZ логов (по умолчанию UTC) |

`make up` без `.env` падает с понятным сообщением («cp .env.example .env»), не поднимая стек с
пустыми кредами. Генерируемые из env артефакты (`infra/trino/auth/password.db`,
`infra/trino/auth/trino.p12`) — gitignored, создаются на каждый `make up`.

## 9. Модель доступа / аутентификация

| Сервис | Аутентификация |
|---|---|
| Grafana | admin-логин/пароль из env |
| MinIO Console/API | root-креды из env |
| **Trino** | **password-аутентификация поверх HTTPS** (см. ниже), пользователь `loftnav` |
| PostgreSQL | только из `data_net`, креды из env (host-порт не публикуется) |

Периметр = локальная машина (все host-порты на `127.0.0.1`, single-user). Ролей продукта нет.

## 10. Ресурсы (NFR-002) и требования к Docker Desktop VM

| Сервис | `mem_limit` | Примечание |
|---|---|---|
| trino | 2816m | heap `-Xmx1792m` + ~1 GB off-heap (mem_limit > Xmx — иначе OOM-kill) |
| minio | 1024m | |
| postgres | 768m | |
| grafana | 512m | |
| minio-init | 128m | one-shot, завершается |
| **Итого (steady)** | **≈5120m** | ≤ 6 GB (NFR-002) |

CPU-лимиты намеренно не заданы (медленнее холодный JVM-старт без пользы).
**Docker Desktop VM: минимум 8 GB (впритык), рекомендуется 10 GB.** Проверено на 8.2 GB VM.

## 11. Производительность старта (NFR-001, замерено на машине владельца, 8.2 GB VM, тёплый кэш)

| Метрика | Порог NFR-001 | Факт |
|---|---|---|
| тёплый `make up` → все healthy + bootstrap | ≤ 120 с | **~34–40 с** |
| `make smoke` (pytest) целиком | ≤ 90 с | **~1.4–5.3 с** (wall с make-обвязкой ~5–9 с) |
| таймаут каждой сетевой проверки smoke | ≤ 30 с | 30 с (per-request) |

Первый (холодный) `make up` с pull образов — дольше на время загрузки (~несколько минут,
зависит от сети); healthcheck'и с `start_period` (Trino 90 с под холодный JVM) не «ложно падают».

_Дата замера: 2026-07-20 (машина владельца, 8.2 GB VM, тёплый кэш образов)._
**Переизмерить при изменении состава стека** (новый сервис, смена лимитов/heap, апгрейд образов).

## 12. Make-цели (BSD/macOS-совместимо)

| Цель | Действие |
|---|---|
| `make up` | проверка Docker/`.env` → генерация auth-артефактов → `pull` → `up -d --wait` → bootstrap namespace'ов |
| `make down` | `docker compose down` **БЕЗ `-v`** (volumes сохраняются, I-2) |
| `make smoke` | `pytest -q tests/smoke` (round-trip) |
| `make bootstrap` | идемпотентный bootstrap namespace'ов medallion |
| `make ps` / `make logs` | диагностика |

## 13. Наблюдаемость, логи, OOM-runbook (NFR-004, I-9)

Все сервисы: `json-file` logging-driver, `max-size=10m`, `max-file=10` (≥ 7 дней истории при
демо-нагрузке). Чтение: `make logs` или `docker logs loftnav-<сервис>`. Healthcheck у 100%
сервисов; `make ps` — статусы.

**Runbook OOM (exit 137 / медленный/падающий сервис):**
- `docker inspect --format '{{.State.OOMKilled}}' loftnav-trino` — был ли OOM-kill;
- `docker inspect --format '{{.State.ExitCode}}' loftnav-<сервис>` — код 137 = kill по памяти;
- `docker stats --no-stream` — фактическое потребление против `mem_limit`;
- Trino heap-dump при OOM: `-XX:+HeapDumpOnOutOfMemoryError` (в `infra/trino/jvm.config`);
- лечение: поднять VM Docker Desktop (10 GB) либо снизить `-Xmx`/`query.max-memory-per-node`.

## 14. ⚠️ Разрушающие операции и бэкап

- `docker compose down -v` — **вне штатных make-целей**: удаляет volumes (каталог + все данные)
  **безвозвратно**. Штатный `make down` volumes НЕ трогает. Перед `down -v` — осознанное решение.
- Автобэкап volumes в 001 не реализован (out of scope); механизм — в отдельной фиче. Ручной бэкап:
  `docker run --rm -v loftnav_minio_data:/data -v "$PWD":/b alpine tar czf /b/minio.tgz -C /data .`
  (аналогично для `loftnav_pg_data`).

## 15. Заметки для фич-продолжений

- **Loader 002** контейнеризуется с dual-membership `app_net` + `data_net` (нужен и app-границе, и
  data-сети для MinIO raw); использует `src/loftnav/trino_client.py` как io-адаптер (I-4).
- **Grafana 005** добавляет только файлы в `infra/grafana/provisioning/{datasources,dashboards}/`
  (в 001 пусто, `.gitkeep`) — compose не трогает; datasource Trino подключать по `trino:8443`
  (HTTPS, password auth, TLS skip-verify).
- **Least-privilege MinIO** (loader→raw, Trino→warehouse) — отложено (MVP использует общие
  root-креды); кандидат в отдельную фичу.

## 16. Отклонения от плана (as-built, обоснование — I-13)

| Область | План | Факт | Причина |
|---|---|---|---|
| Trino auth | password по HTTP + `allow-insecure-over-http` (T6/FR-015) | password по **HTTPS** (self-signed, `infra/trino/gen-tls.sh`); внутренний HTTP:8080 не публикуется | Trino ПО ДИЗАЙНУ отклоняет проверку пароля по небезопасному HTTP (`allow-insecure-over-http` разрешает лишь беспарольный доступ). HTTPS обязателен — эмпирика I-13. Публикуемый host-порт остаётся 8080 (в белом списке FR-003), маппится на container:8443 |
| shared-secret | не упомянут | добавлен `internal-communication.shared-secret` (env `TRINO_INTERNAL_SECRET`) | Trino требует его при любой включённой аутентификации (даже single-node) |
| Служебные таблицы каталога | предполагалось авто-создание JdbcCatalog | пред-создаются init-скриптом Postgres (`infra/postgres/init/01-iceberg-catalog.sql`, точный V0-DDL Iceberg 1.11); Trino до-мигрирует до V1 | Iceberg 1.11 default `init-catalog-tables=false`, а Trino это свойство не публикует (валит старт) — эмпирика I-13 |
| `query.max-memory-per-node` | 1.5GB (T1) | **1.4GB** | при heap 1792m Trino валидирует `per-node + heap-headroom(300MB) ≤ heap`; 1536+300 > 1792 не стартует. Xmx1792m сохранён (off-heap-бюджет T2) |
| pytest | 8.x (T5) | **9.1.1** | актуальная версия на момент реализации; плагинов не используем |
| grafana | «актуальный мажор» | **12.3.8** | текущий стабильный |
| Доп. файлы | — | `infra/trino/{node-less}`, `password-authenticator.properties`, `gen_password.py`, `gen-tls.sh`, `infra/postgres/init/` | реализация auth/каталога (в рамках `infra/`) |

Число контейнеров осталось 5 (minio, postgres, trino, grafana, minio-init) — как в плане.
