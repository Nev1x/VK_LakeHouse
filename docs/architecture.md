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
- **Grafana 005** добавляет provisioning-файлы в `infra/grafana/provisioning/{datasources,dashboards}/`
  И **аддитивно правит environment сервиса grafana в compose** (плагин + креды — см. §Dashboards;
  прежняя заметка «compose не трогает» снята: healthcheck/сети/volumes/порты не меняются, только env);
  datasource Trino подключается по `trino:8443` (HTTPS, password auth, TLS skip-verify).
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

---

# Ingestion (фича 002 — универсальный загрузчик, as-built)

CLI `loftnav ingest <файл|папка>`: файлы о квартирах (CSV/XLSX/JSON/JSONL) → immutable raw-копия в
MinIO → типизированный append в `iceberg.bronze.<источник>` через Trino → невалидные строки в
quarantine → append-only журнал `iceberg.ops.pipeline_runs`. Файл — логическая единица; сбой одного
файла не роняет батч (I-8).

## Конвейер (на файл)

`hash → журнальный статус (skip/replay) → raw PUT → read (потоково) → schema inference →
bronze (parametrized INSERT) → rejects → ОДИН INSERT в журнал (try/finally)`.

## CLI / Make

| Команда | Действие |
|---|---|
| `make ingest FILE=<path>` | загрузить файл/папку |
| `make ingest-demo` | загрузить `tests/fixtures/ingestion/` |
| `loftnav ingest <path...> [--source <имя>]` | прямой CLI (console_script) |

**Exit codes (FR-012):** `0` — всё успешно/skipped; `1` — все файлы провалились; `2` — частично
(демо возвращает 2 из-за намеренно битого файла). Итоговая сводка по файлам — в stdout,
structured key=value логи с `run_id` — в stderr.

## Форматы и лимиты

CSV (автодетект `,`/`;`/tab + кодировки utf-8/utf-8-sig/cp1251, бинарный файл → failed),
XLSX (openpyxl `read_only+data_only`, каждый лист = источник `<база>_<лист>`, merged cell → NULL
в не-anchor ячейках), JSON/JSONL (вложенные структуры → VARCHAR(JSON)). Лимиты (env,
переопределяемы): `LOFTNAV_MAX_FILE_MB` (500), поле `LOFTNAV_MAX_FIELD_BYTES` (1 MB),
`LOFTNAV_READ_CHUNK_ROWS` (5000), `LOFTNAV_INSERT_CHUNK_ROWS` (1000). Новый формат = новый
reader-модуль (`ingest/readers/`), диспетчер не трогается.

## Schema inference

Примитивы Iceberg: BOOLEAN/BIGINT/DOUBLE/DATE/TIMESTAMP/VARCHAR. Тип выводится по первому
read-чанку; конфликт типов внутри чанка → VARCHAR; запятая-десятичная (`1234,56`) остаётся VARCHAR
(нормализация — работа 003); вложенный JSON → VARCHAR. Строки, не приводящиеся к типу колонки
(в т.ч. нарушающие тип на поздних чанках или несовместимые со схемой существующей таблицы), →
quarantine. Санитизация ВСЕХ идентификаторов — единый `sanitize_identifier()` (`[a-z0-9_]`, не с
цифры, дедуп, non-ASCII→`_`); пользовательский `_`-префикс → `u_` (служебный `_` зарезервирован).
Значения в SQL — ТОЛЬКО bind-параметры; идентификаторы — санитизированы и двойными кавычками (I-7).

## Контракт bronze-таблиц

`iceberg.bronze.<источник>` (`format='PARQUET', format_version=2` — row-level DELETE для replay).
Data-колонки + служебные: `_run_id`, `_content_hash`, `_source_file`, `_ingested_at`. VARCHAR без
длины (unbounded). Эволюция строго additive: `ALTER TABLE ADD COLUMN` (nullable); существующая
колонка авторитетна; несовместимый тип вне промоций (INTEGER→BIGINT, BIGINT→DOUBLE, REAL→DOUBLE) →
файл `failed` «schema conflict» (I-6). Прямая запись parquet в warehouse запрещена (I-4).

## Контракт журнала (frozen, I-3/I-6)

`iceberg.ops.pipeline_runs` (namespace `ops` — bootstrap, константа `OPS_NAMESPACES`, НЕ слой
medallion). Колонки: `run_id, stage, started_at, finished_at, source_file, content_hash,
target_table, rows_ok, rows_quarantined, schema_json, status, error_message`. **ОДИН INSERT на
прогон файла** (try/finally); НИКАКИХ UPDATE (append-only). `stage='ingest'` (003/006 добавят свои).
Статусы: `success` (0 отбраковок) / `partial` (были отбраковки) / `failed` (сбой файла) / `skipped`
(идемпотентный повтор). Для каждого прогона `rows_ok + rows_quarantined` = обработанные строки
(вход дашборда 005).

## Quarantine

`iceberg.quarantine.bronze_<источник>_rejects` (fv2): `run_id, source, raw_record` (JSON as-is),
`reason`, `rejected_at`, `layer`. Модуль `quarantine.py` переиспользует 003. Невалидные строки не
дропаются молча (I-2).

## Raw (immutable, I-2)

Content-addressed ключ `raw/<sha256-hex>/<безопасное-имя>` в bucket `raw`. Одинаковые байты → один
ключ → идемпотентный PUT; перезапись другим содержимым по тому же ключу невозможна by construction.
Исходное имя файла as-is живёт в журнале (`source_file`).

## Идемпотентность и replay (FR-010)

Перед обработкой — SELECT последнего статуса по `content_hash`: `success`/`skipped` → **skip**
(журнал `skipped`); `failed`/`partial` → **replay**: `DELETE FROM bronze WHERE _content_hash = ?`
(bind-параметр, только строки этого файла) → повторная вставка. **I-2-трактовка:** raw абсолютно
immutable и не затрагивается; DELETE применяется ТОЛЬКО к строкам прогона, никогда не имевшего
статуса `success` (мусор незавершённой попытки, не зафиксированная история); Iceberg-снапшоты не
expire (time-travel сохраняет их); quarantine не трогается; журнал получает НОВУЮ запись (старая не
редактируется). Конкурентность (I-15): файловый lock `${TMPDIR}/loftnav-ingest.lock`
(`O_CREAT|O_EXCL` + pid, stale-lock перехватывается) — второй запуск получает читаемую ошибку.

## Ограничения и осознанные риски

- **PII в quarantine as-is (SEC-5):** отбракованные записи хранятся сырыми — осознанный риск
  локальной single-user платформы (I-1); маскирование — кандидат отдельной фичи.
- **Рост журнала (PERF-4):** идемпотентность делает full-scan по `content_hash` — принято для
  демо-масштаба; партиционирование/индекс — ревизия при >10^5 прогонов.
- **JSON-массив без стриминга:** файл-массив > лимита размера → failed; для больших объёмов — JSONL.
- **Откат:** additive-колонки bronze при необходимости дропаются вручную без потери остальных данных;
  разрушающих миграций нет.

## Пины зависимостей (002)

`pandas==3.0.3`, `openpyxl==3.1.5`, `boto3==1.43.51` (runtime); `requests==2.34.2` (dev —
использует smoke/интеграционные тесты; в 001 доезжал транзитивно). Стратегия INSERT выбрана
spike-тестом на живом Trino 483 (см. ниже).

## Отклонения от плана 002 (as-built, обоснование I-13)

| Область | План | Факт | Причина |
|---|---|---|---|
| Стратегия INSERT | execute vs executemany (spike) | multi-row `INSERT ... VALUES (?,..),(?,..)`, ОДИН execute на чанк | spike: `executemany` trino-клиента шлёт построчно (N запросов = N снапшотов = мелкие файлы); multi-row single-execute = один снапшот на чанк |
| Инференс «уточнение по ходу» (T6) | промоция типа по ходу файла | инференс по первому read-чанку; строки, нарушающие тип на поздних чанках, → quarantine | проще и спец-совместимо (US-5): не переписываем колонку mid-batch; конфликт ВНУТРИ чанка → VARCHAR |
| Идемпотентный статус (FR-010) | «success → skip» | `success` И `skipped` → skip | иначе повтор после skip видел бы last_status=`skipped` и делал бы свежий append (дефект найден и закрыт в этом же цикле) |

---

# Transform (фича 003 — silver-нормализация, as-built)

CLI `loftnav transform`: разношёрстные bronze-таблицы → единая `iceberg.silver.apartments_clean`
по декларативным TOML-маппингам per-источник (новый источник = конфиг, не код). Приведение
типов/единиц, intra-source дедуп (MERGE, last-write-wins), инкрементальность по журналу,
quarantine непрошедших нормализацию, явный reprocess при смене конфига.

## Конвейер (на источник × bronze-партицию)

`config (fail-fast валидация) → config-hash gate → anti-join новых партий → read bronze (fetchmany)
→ normalize (примитивы) → dedup (external_id, last-write-wins) → MERGE в silver → rejects → журнал`.

## CLI / Make

| Команда | Действие |
|---|---|
| `make transform` / `loftnav transform` | обработать все источники с конфигами |
| `loftnav transform --source <имя>` | только один источник |
| `loftnav transform --reprocess <имя>` | DELETE партиции источника + полный пересчёт |
| `make transform-demo` | ingest демо-источников (t_avito/t_cian/t_domclick) + transform |

Exit codes: `0` — всё success/skipped; `1` — все источники failed; `2` — частично.

## Схема `iceberg.silver.apartments_clean` (FROZEN, additive-only для 004/006)

`WITH (format='PARQUET', format_version=2, partitioning=ARRAY['source'])`.

| Колонка | Тип | Прим. |
|---|---|---|
| `id` | varchar | sha256 (length-prefixed `source`:`external_id` — анти-коллизия) |
| `source`, `external_id` | varchar | ключ идентичности (партиция = source) |
| `price_rub` | **decimal(12,2)** | точная арифметика для агрегатов 004 |
| `area_m2` | **decimal(8,2)** | |
| `rooms`, `floor`, `floors_total`, `metro_minutes` | bigint | |
| `address`, `district`, `style`, `renovation_style` | varchar | |
| `has_renovation`, `has_furniture` | boolean | |
| `photo_urls` | varchar | JSON-массив as-is |
| `listed_at` | timestamp | |
| `_source_run_id`, `_source_content_hash`, `_mapping_config_hash` | varchar | провенанс |
| `_ingested_at`, `_transformed_at` | timestamp | last-write-wins по `_ingested_at` |
| `_transform_run_id` | varchar | |

Обязательность (`id/source/external_id/price_rub/area_m2`) — через quarantine, не SQL-constraint.
`silver_columns_version = 1` (в `schema_json` журнала).

## Формат mapping-конфига (`configs/mapping/<источник>.toml`)

tomllib (stdlib, 0 новых зависимостей). Закрытый набор примитивов, НИКАКОГО eval/exec (I-7/I-14).
Порядок применения: `regex_replace → regex_extract → enum_map | cast → unit_convert → default`.

```toml
[meta]
external_id = "id"            # bronze-колонка identity (нет → синтетический хэш полей, best-effort)

[fields.price_rub]
input = "price"               # bronze-колонка
cast = "decimal"             # decimal | bigint | boolean | timestamp | varchar
unit_convert = { from = "thousands_rub", to = "rub" }   # факторы: thousands_rub/mln_rub/sotka…

[fields.area_m2]
input = "area"
regex_replace = { pattern = ",", replacement = "." }    # запятая-десятичная → точка ДО cast
cast = "decimal"

[fields.has_renovation]
input = "renov"
enum_map = { "евро" = true, "черновая" = false }        # СТРОГО dict exact-match (casefold+trim)
```

Валидация при старте (fail-fast): неизвестное silver-поле/ключ/cast → ошибка; input-колонка
отсутствует в bronze-схеме (DESCRIBE) → ошибка с именем колонки; непокрытые bronze-колонки → warning.
Деньги/площадь: `str → Decimal → quantize(0.01)` — БЕЗ промежуточного float (точность). Regex —
с cap длины значения `LOFTNAV_REGEX_VALUE_CAP` (64KB) до применения (ReDoS defense-in-depth).

## Инкрементальность и reprocess (FR-007/FR-008)

Единица обработки — (источник × bronze `_content_hash`). Anti-join по журналу `stage='transform'`:
партиция со статусом success/skipped/**partial** пропускается (partial терминален — MERGE
идемпотентен, повтор лишь копил бы quarantine); переобрабатывается только `failed`. Пустой
инкремент → 0 партий, быстрый выход. `_mapping_config_hash` конфига пишется в silver-строки и в
`schema_json` журнала; при расхождении текущего хэша с последним успешным — transform источника
**останавливается** с подсказкой `loftnav transform --reprocess <источник>`. Reprocess =
`DELETE FROM apartments_clean WHERE source = ?` (bind, partition prune) + полная переигровка.

## I-2-трактовка (MERGE / reprocess)

- **MERGE** — точечный ACID-upsert по known identity (source, external_id), last-write-wins по
  `_ingested_at` — это НЕ переписывание таблицы (аналог replay 002). Iceberg-снапшоты не expire
  (time-travel сохраняет историю). Значения — только bind-параметры; source типизирован через CAST
  (устойчиво к all-NULL колонкам). Spike на Trino 483 подтвердил MERGE INTO … USING (VALUES …).
- **Reprocess** — bulk-перезапись партиции источника, но по ЯВНОМУ решению оператора (флаг
  `--reprocess`); журнал append-only получает новые записи; raw не затрагивается.

## Единый lock конвейера (FR-012, I-15)

`${TMPDIR}/loftnav-pipeline.lock` — общий с ingest: transform не идёт параллельно ни с ingest, ни
с другим transform (грубая сериализация — осознанный MVP-компромисс).

## Рефакторинги переиспользования (FR-013, поведение 002 без изменений)

- `src/loftnav/ident.py` — нейтральный санитайзер/квотер идентификаторов (реэкспорт из
  ingest/inference для совместимости).
- `src/loftnav/chunked_insert.py` — общий байт-бюджетный multi-row хелпер (estimate/prefix/chunk/
  insert); используют bronze_writer, quarantine, silver_writer.
- `runlog.last_status(conn, content_hash, stage)` — ОБЯЗАТЕЛЬНЫЙ stage-фильтр (у ingest и transform
  один content_hash, но разные стадии); call-site ingest обновлён. Регрессия 002 зелёная.

## Ограничения и осознанные риски

- **Cross-source дедуп НЕ гарантируется** — один и тот же объект из двух источников = две строки
  (разные `source`); fuzzy/ML-matching — кандидат рядом с 006.
- **Полнота полей зависит от источника** — конфиг маппит только доступные колонки; непокрытые
  silver-поля = NULL. Обязательны только price_rub/area_m2 (иначе строка в quarantine).
- **Рост журнала (PERF-4, наследие 002)** распространяется на transform (full-scan по content_hash
  и config-hash) — принято для демо-масштаба; партиционирование журнала — ревизия при росте.
- **Merge-on-read read-amplification / компакция** Iceberg fv2 — вне MVP (кандидат: периодический
  OPTIMIZE).
- **PII в quarantine as-is** — как в 002 (локальная single-user платформа, I-1).
- **Синтетический external_id** (источник без стабильного id) — best-effort хэш нормализованных
  полей: правка текста → переиндексация строки (задокументированная деградация).

## Отклонения от плана 003 (as-built, обоснование I-13)

| Область | План | Факт | Причина |
|---|---|---|---|
| Демо-источники | конфиги под фикстуры 002 (apartments/flats/listings_flats) | отдельные демо-источники t_avito/t_cian/t_domclick | фикстуры 002 не содержат обязательных price+area (только apartments имеет area) — маппинг невозможен; источники 002 без конфига демонстрируют FR-010 (skip) |
| id-хэш | `sha256(f"{source}:{external_id}")` (T7) | length-prefix `sha256(f"{len(source)}:{source}:{external_id}")` | наивная конкатенация коллизирует при ':' в external_id (аудит #15) — префикс длины делает инъективной |
| Инкремент. статус | success/skipped → skip; failed/partial → reprocess (FR-007) | **partial тоже терминален** (skip) | MERGE идемпотентен, но re-run partial копил бы quarantine и ломал идемпотентность (0 партий на повторе); переобрабатывается только failed |
| MERGE source | `USING (VALUES …)` | `USING (SELECT CAST(...) FROM (VALUES …))` | явный CAST — устойчивость к all-NULL колонкам (тип не выводится из NULL-литералов) |

---

# Gold (фича 004 — витрины и feature-таблица, as-built)

CLI `loftnav build-gold`: из `silver.apartments_clean` строятся три материализованные витрины-агрегата
(вход дашбордов 005) и row-level feature-таблица `apartments_features` (вход 006). Полный
детерминированный пересчёт из silver, атомарная замена, журнал `stage='build_gold'`. Схемы gold —
FROZEN (I-6): их захардкодят 005 и 006.

## CLI / Make

| Команда | Действие |
|---|---|
| `make build-gold` / `loftnav build-gold` | пересчитать все витрины + features |
| `loftnav build-gold --only <mart>` | одна витрина/таблица |
| `make build-gold-demo` | ingest демо → transform → build-gold (данные для QA 005/006) |

Exit codes: `0` — все success; `1` — все failed; `2` — частично.

## Витрины (frozen, additive-only)

**`iceberg.gold.mart_price_area_by_district`** — `district` (COALESCE→'unknown'), `listing_count`,
`avg_price_rub`, `median_price_rub`, `min/max_price_rub`, `avg_price_per_m2`, `avg_area_m2`,
`_computed_at`, `_gold_run_id`. Медиана — `approx_percentile(CAST(price_rub AS DOUBLE), 0.5)` с
явным `CAST(... AS DECIMAL(12,2))`. `price_per_m2` через `NULLIF(area_m2, 0)`.

**`iceberg.gold.mart_style_renovation_furniture`** — `style_norm`/`renovation_style_norm`
(`lower(trim())`, COALESCE→'none'), `has_renovation`, `has_furniture`, `listing_count`,
`avg_price_rub`, `median_price_rub`, `avg_area_m2`, `is_small_sample` BOOLEAN
(`listing_count < LOFTNAV_GOLD_SMALL_SAMPLE`, default 3), `_computed_at`, `_gold_run_id`.

**`iceberg.gold.mart_listing_dynamics`** — `load_date` DATE (`DATE(_ingested_at)` из silver, НЕ из
pipeline_runs — I-4), `listings_added`, `listings_added_cumulative` (window sum). Date-spine
(`sequence(min,max,INTERVAL '1' DAY)`) убирает дыры в ряду (US-3).

Каждая агрегатная колонка — ЯВНЫЙ `CAST(... AS DECIMAL(p,s))` (не вывод CTAS). Определения — код
(`src/loftnav/gold/marts.py`), tuple-driven, явный список колонок (`SELECT *` структурно невозможен —
additive-колонка silver не просочится в frozen-схему gold).

## `apartments_features` (frozen, вход 006; fv2)

`id/source/external_id` VARCHAR; `price_rub` DECIMAL(12,2), `area_m2` DECIMAL(8,2), `price_per_m2`
DECIMAL(12,2) nullable (NULL при area=0 — NULLIF); `rooms/floor/floors_total/metro_minutes` BIGINT;
`floor_ratio` DOUBLE nullable (NULL при floors_total NULL/0); `district/style/renovation_style`
VARCHAR; `has_renovation/has_furniture` BOOLEAN; `listed_at` TIMESTAMP; `photo_urls` VARCHAR
(JSON as-is, passthrough для CV-фич 006 — gold не парсит); служебные `_silver_snapshot_id`,
`_source_transform_run_id`, `_gold_run_id` VARCHAR, `_computed_at` TIMESTAMP.

**`is_loft` BOOLEAN — ВСЕГДА NULL** (target-заготовка). Эвристика `style ILIKE '%loft%'` ЗАПРЕЩЕНА
как лже-таргет/утечка (I-11): разметка «лофт/не-лофт» — вне платформы (устав/006). Decision record:
реальный `is_loft` появится при разметке в 006; до тех пор колонка резервирует контракт схемы.

## Материализация (spike-решение)

**CREATE OR REPLACE TABLE `<mart>` WITH (format_version=2) AS SELECT `<явные колонки>` FROM
silver FOR VERSION AS OF `<snapshot_id>`.** Spike на Trino 483 подтвердил: CREATE OR REPLACE на
JDBC-каталоге АТОМАРЕН — таблица существует непрерывно (Iceberg заменяет метаданные одним коммитом),
старый snapshot остаётся в истории (time-travel в пределах генерации). Читатель дашборда никогда не
видит полу-пересчитанную витрину и не получает «table not found» (в отличие от rename-swap, у
которого есть sub-секундное окно между двумя RENAME). `FOR VERSION AS OF <snapshot>` пинует чтение
silver на снапшот, зафиксированный на старте build — детерминизм (NFR-004).

## Журнал (FR-008)

Одна запись `stage='build_gold'` на витрину: `target_table`=имя витрины,
`content_hash`=**snapshot_id silver** (семантика переопределена — воспроизводимая привязка «на каком
состоянии silver построено», без хэша миллионов строк; из
`iceberg.silver."apartments_clean$snapshots"` ORDER BY committed_at DESC LIMIT 1),
`rows_ok`=строк на выходе, `schema_json`={gold_columns_version}. `$snapshots`-имя строится ОТДЕЛЬНОЙ
функцией (`marts.snapshots_relation`), НЕ через ident (`$` отклоняется quote_ident) — ident.py не
трогается.

## I-2-трактовка (полный пересчёт)

Все витрины и features — полный rebuild из silver каждый прогон (агрегаты — функция всей выборки;
инкрементальная медиана некорректна без хранения распределения). Это штатный режим ПРОИЗВОДНОГО
слоя, не «переписывание источника без решения владельца»: gold детерминированно вычислим из silver,
Iceberg-снапшоты витрин не expire в пределах генерации. Аналог reprocess 003. Откат (SHOULD-3):
`build-gold` из предыдущей ревизии silver/кода воспроизводит витрины; time-travel витрины —
`FOR VERSION AS OF` до DROP старого снапшота (кросс-прогонная история не гарантируется — SHOULD-1).
`fv2` = format_version=2 (текущий стандарт Iceberg, не «предыдущая версия контракта» — SHOULD-2).

## Конкурентность, cleanup, run_id

Общий pipeline-lock с ingest/transform (`loftnav-pipeline.lock`, FR-009). `run_id` (uuid4.hex)
валидируется `^[a-f0-9]{32}$` перед использованием как значения. Осиротевшие временные таблицы
`<mart>__build_`/`__old_` вычищаются `SHOW TABLES FROM iceberg.gold` + Python `startswith` (НЕ SQL
LIKE — там `_` wildcard); при CREATE OR REPLACE временных таблиц не образуется, чистка — защита от
легаси/крашей.

## Ограничения и риски

- **is_loft always NULL** — documented gap лофт-маркеров; координация с 006 при разметке.
- **Cross-source дубли инфлируют count** (наследие 003: cross-source дедуп не гарантируется) — count
  витрин может завышаться; документировано.
- **approx-медиана** — приближённая (approx_percentile), детерминирована на фиксированном snapshot
  (spike: стабильна ×5); осознанная потеря точности для дашборда. Точный перцентиль — при необходимости.
- **Full-scan агрегатов/features** (наследие PERF-4) — принято для демо-масштаба; features на
  инкрементальный MERGE — кандидат ревизии при росте.

## Отклонения от плана 004 (as-built, обоснование I-13)

| Область | План | Факт | Причина |
|---|---|---|---|
| Материализация | rename-swap (build→rename old→rename build→drop old) как default; CREATE OR REPLACE если spike подтвердит | **CREATE OR REPLACE** | spike подтвердил атомарность на Trino 483; строго лучше rename-swap (нет not-found окна для читателя, FR-005/US-5); time-travel сохраняется. Временных `__build_`/`__old_` таблиц нет → cleanup по префиксу оставлен как защита от легаси/крашей; run_id всё равно валидируется regex |

---

# Dashboards (фича 005 — Grafana как код, as-built)

Дашборды Grafana через provisioning: Trino-datasource + два дашборда («Операции платформы» из
`ops.pipeline_runs`, «Квартиры» из gold-витрин 004). Поднимаются из `infra/grafana/provisioning/`
при `make up`, без ручной настройки. Падение Grafana не влияет на пайплайны (I-8).

## Структура provisioning (`infra/grafana/provisioning/`, монтируется `:ro`)

| Файл | Роль |
|---|---|
| `datasources/trino.yaml` | datasource `trino-datasource` → `https://trino:8443` |
| `dashboards/dashboards.yaml` | file-provider, грузит все `*.json` из каталога |
| `dashboards/platform-ops.json` | дашборд «Операции платформы» (uid `loftnav-platform-ops`) |
| `dashboards/apartments.json` | дашборд «Квартиры» (uid `loftnav-apartments`) |

## Spike-результат (эмпирика на живом Grafana 12.3.8 — README не даёт примера)

| Вопрос | Факт |
|---|---|
| Плагин | `trino-datasource` **v1.0.11**, **signature: valid** (подписан community — unsigned-риск снят) |
| Установка | **`GF_PLUGINS_PREINSTALL_SYNC="trino-datasource@1.0.11@<github-zip-url>"`** (GF_INSTALL_PLUGINS deprecated на 12.x и НЕ парсит URL-форму) |
| Источник | **GitHub-релиз** (каталог grafana.com в этом окружении отдаёт **HTTP 451** — заблокирован; GitHub доступен). Пин версии сохранён |
| env-подстановка | форма **`${VAR}`** (не `$__env{}`, не `$VAR`-обязательно) — `${TRINO_USER}`→`loftnav` подставился |
| auth-поля | **`basicAuth: true` + `basicAuthUser: ${TRINO_USER}` + `secureJsonData.basicAuthPassword: ${TRINO_PASSWORD}` + `jsonData.tlsSkipVerify: true`** |
| health | `/api/datasources/uid/loftnav-trino/health` → **status: OK, «Data source is working»** против trino:8443 |
| target-формат | `rawSql` + `format` (ЧИСЛОВОЙ enum sqlds: 1=table, 0=timeseries), макросы `$__timeFrom()/$__timeTo()/$__timeFilter(col)` работают |

## compose env grafana (аддитивно — §Notes обновлён)

Добавлено ТОЛЬКО в `environment` сервиса grafana (healthcheck/networks/volumes/ports не тронуты):
`GF_PLUGINS_PREINSTALL_SYNC` (плагин с пином, GitHub URL), `GF_PLUGINS_ALLOW_LOADING_UNSIGNED_PLUGINS`
(defensive — плагин фактически подписан), `TRINO_USER`, `TRINO_PASSWORD` (для `${VAR}`-подстановки в
datasource YAML). Секреты — только env-ссылки в git-файлах; реальные значения в container-env
(видны через `docker inspect`, но не в репозитории — «0 plaintext» относится к git).

## Панели (все journal-панели bounded, I-15)

**«Операции платформы»** (источник — `ops.pipeline_runs` напрямую, I-4): последний прогон по stage
(`row_number` + `WHERE started_at >= $__timeFrom()`); свежесть (`date_diff` от `max(finished_at)`,
thresholds на панели); принято/отбраковано по stage (`BETWEEN $__timeFrom() AND $__timeTo()`);
quarantine-таблицы через `iceberg.information_schema.tables WHERE table_schema='quarantine'`
(bounded by construction, не чтение reject-таблиц); лента failed с `error_message`
(`WHERE started_at >= $__timeFrom() ... ORDER BY started_at DESC LIMIT 200`). **Ни одна панель не
делает unbounded full-scan** растущего журнала (append-only, I-3).

**«Квартиры»** (gold 004): цены/площади по district (**atemporal**, фильтр по template-переменной
`district`); срезы style/renovation/furniture с видимым `is_small_sample` (**atemporal**); динамика
`mart_listing_dynamics` — **временной ряд по `load_date` с time-picker**
(`WHERE load_date BETWEEN CAST($__timeFrom() AS DATE) AND CAST($__timeTo() AS DATE)`). Витрины
district/style atemporal by construction (кардинальность ограничена числом районов/сегментов) — не
наследуют глобальный time-picker (иначе данные «пропадают» при узком range).

Datasource в панелях — по переменной **`${DS_TRINO}`** (тип datasource, авто-резолв к дефолтному
Trino), НЕ хардкоженный uid (иначе «Datasource not found» на чистой машине). Auto-refresh **off**
(`refresh: ""`) в обоих дашбордах (NFR-006 bounded-нагрузка).

## Гарантии и риски

- **I-4/I-1 сетевая гарантия:** grafana ∈ `public_net` + `app_net`, НЕ в `data_net` — физически нет
  пути к MinIO/Postgres; все данные — только через Trino (datasource). Дашборды не читают
  parquet/reject-таблицы напрямую.
- **I-8 изоляция:** остановка grafana → `make smoke` и пайплайны зелёные (проверено); Trino down →
  ошибка панели (не блокер, browser-QA не заводит тикет).
- **Офлайн-риск (accepted):** первый `make up` на чистом volume требует сеть для скачивания плагина
  (~60 MB с GitHub); дальше кэшируется в `grafana_data`. Провал скачивания = grafana не healthy =
  блокер (документированное требование сети на первый up). Control-plane egress (ПО), не data (I-1).
- **Плагин подписан** (signature: valid) — риск unsigned-плагина из плана снят; `ALLOW_UNSIGNED`
  оставлен defensive (безвреден при подписанном плагине).
- **Секреты — PRIMARY unit-тест** (`tests/grafana/unit`): парсит YAML/JSON, требует `password`/
  `secureJsonData.*` начинаться с `$`. Хук-secret-скан не ловит generic-пароль — вторичный слой.
- **generated-дашборды AGENTS.md ≠ Grafana provisioning JSON:** запрет ручной правки generated —
  про артефакты `scripts/`; provisioning-JSON правятся через Grafana UI export → коммит (intent 005).

## Отклонения от плана 005 (as-built, обоснование I-13)

| Область | План/spec | Факт | Причина |
|---|---|---|---|
| Установка плагина | `GF_INSTALL_PLUGINS=trino-datasource@<пин>` из каталога grafana.com | `GF_PLUGINS_PREINSTALL_SYNC` c GitHub-URL | grafana.com отдаёт 451 в окружении; GF_INSTALL_PLUGINS deprecated и не парсит URL на 12.3.8; GitHub-релиз (официальный, с пином) доступен |
| Провайдеры дашбордов | два файла `ops.yaml` + `apartments.yaml` | один `dashboards.yaml` (file-provider на каталог) | два провайдера на один каталог грузили бы оба JSON дважды; один провайдер на каталог — стандартный паттерн Grafana |
| unsigned-плагин | decision record «accepted unsigned risk» | плагин фактически **подписан** (signature: valid) — риск снят | эмпирика spike |
