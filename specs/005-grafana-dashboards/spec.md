# Spec 005 — grafana-dashboards (дашборды как код)

Статус: stage-1 draft → аудит stage-2. Scope: feature. Intent: `specs/005-grafana-dashboards/intent.md`.

## Overview

Дашборды Grafana как код (provisioning): Trino-datasource + два дашборда — «Операции платформы»
(прогоны/quarantine/свежесть/ошибки из `ops.pipeline_runs`) и «Квартиры» (агрегаты из
gold-витрин). Всё поднимается из `infra/grafana/provisioning/` при `make up`, без ручной
настройки. Падение Grafana не влияет на пайплайны (I-8). Тестируют browser-QA
(renata/semiglazka). **WHY:** первая точка, где данные платформы становятся видимы человеку;
завершает наблюдаемость (I-9) поверх готовых gold/журнала.

## User Stories

- **US-1 Здоровье пайплайна.** Владелец за 10с видит статус последнего прогона каждого stage
  (ingest/transform/build_gold). _Приёмка:_ дашборд «Операции» показывает status+время
  последнего прогона по stage без ручного SQL.
- **US-2 Качество данных.** Объём отбраковки по прогонам/источникам за период. _Приёмка:_ панель
  rows_quarantined vs rows_ok из journal; список quarantine-таблиц через information_schema
  (без хардкода имён).
- **US-3 Свежесть.** Возраст последнего success по каждому stage. _Приёмка:_ stat-панель
  `now()-max(finished_at)` с настраиваемыми порогами (thresholds на панели, не в SQL).
- **US-4 Аналитика квартир.** Распределения по районам и срезы по стилю/ремонту/мебели,
  динамика. _Приёмка:_ панели из трёх mart_* с живыми данными после build-gold-demo; фильтр
  district как template variable.
- **US-5 Подъём с нуля.** После чистого `make up` (+ build-gold-demo для данных) datasource и
  оба дашборда появляются сами. _Приёмка:_ свежий volume → Grafana UI показывает Trino-datasource
  и оба дашборда из provisioning, без ручных кликов.
- **US-6 Ошибки видны.** Последние failed-прогоны с error_message. _Приёмка:_ table-панель
  run_id/stage/source_file/error_message.

## Functional Requirements

- **FR-001 Datasource provisioning.** `infra/grafana/provisioning/datasources/trino.yaml`:
  `type: trino-datasource`, `url: https://trino:8443` (internal DNS, app_net), `access: proxy`,
  `jsonData.tlsSkipVerify: true` (self-signed 001), user/пароль — ТОЛЬКО через env-подстановку
  Grafana `$VAR`/`${VAR}` (подтверждённый провижининг-синтаксис — НЕ `$__env{}`;
  `secureJsonData.password: ${TRINO_PASSWORD}`, user из `${TRINO_USER}`; никогда plaintext —
  I-7), `isDefault: true`, `editable: false`. Точные имена auth-полей плагина (`jsonData.user`
  vs `basicAuthUser`/`secureJsonData.basicAuthPassword`) и точная форма env-подстановки
  сверяются spike'ом на живом Grafana 12.3.8 (README не даёт готового примера) — критерий
  spike: реальный `/api/datasources/uid/<uid>/health` = OK, не «curl 200».
- **FR-002 Плагин.** `trino-datasource` (Trino community, unsigned): в compose grafana env
  аддитивно `GF_INSTALL_PLUGINS=trino-datasource@<пин>`,
  `GF_PLUGINS_ALLOW_LOADING_UNSIGNED_PLUGINS=trino-datasource`, `TRINO_USER`/`TRINO_PASSWORD`
  (для `$__env`). Версия пинуется (запрет `:latest` по духу 001). Здоровье/сети/volumes/порты
  grafana НЕ меняются.
- **FR-003 Дашборд «Операции платформы».** JSON в `infra/grafana/provisioning/dashboards/
  platform-ops.json` + provider `dashboards/ops.yaml`. Панели (≥3, минимум US-1/2/3):
  статус+время последнего прогона по stage; accepted/rejected во времени (sum rows_ok/
  rows_quarantined по stage); свежесть (age последнего success по stage/target_table); таблица
  failed с error_message (US-6); обзор quarantine-таблиц через `iceberg.information_schema.
  tables WHERE table_schema='quarantine'`. Источник — `ops.pipeline_runs` напрямую через Trino
  (I-4; не через новую витрину — 004 её не строила). **Bounded-выборки (I-15):** `pipeline_runs`
  append-only и не чистится (I-3) → растёт бессрочно; ВСЕ панели журнала обязаны быть
  ограничены: панель failed — `WHERE started_at >= $__timeFrom()` + `ORDER BY started_at DESC
  LIMIT 200`; лента прогонов — тот же time-filter + LIMIT; агрегатные (accepted/rejected,
  свежесть) — с `WHERE started_at >= $__timeFrom() AND started_at <= $__timeTo()`. Ни одна
  панель этого дашборда не делает unbounded full-scan журнала.
- **FR-004 Дашборд «Квартиры».** JSON `dashboards/apartments.json` + provider. Панели (≥3):
  цены/площади по district (mart_price_area_by_district); срезы style/renovation/furniture с
  видимым `is_small_sample` (mart_style_renovation_furniture); динамика load_date
  (mart_listing_dynamics). Все запросы полностью квалифицированы `iceberg.gold.*`; template
  variable `district`. Time-picker: витрины district/style — **atemporal** (агрегаты по всему
  датасету, кардинальность ограничена числом районов/сегментов — bounded by construction,
  I-15), НЕ наследуют глобальный time-picker (иначе данные «пропадают» при узком range).
  `mart_listing_dynamics` — **временной ряд по load_date, использует time-picker** (`WHERE
  load_date` в диапазоне пикера) — это НЕ atemporal-исключение; так выборка bounded диапазоном,
  а не full-scan растущей витрины (I-15).
- **FR-005 Дашборды как код.** JSON лежат ВНУТРИ `infra/grafana/provisioning/dashboards/`
  (единственный смонтированный путь `:/etc/grafana/provisioning:ro`); правки — через Grafana UI
  export → коммит, ручное редактирование сгенерированного JSON запрещено (соглашение intent);
  datasource в панелях ссылается по имени/переменной `${DS_TRINO}`, НЕ по хардкоженному uid
  (иначе provisioning на чистой машине даёт «Datasource not found»).
- **FR-006 Секреты.** 0 plaintext-кредов в git-файлах YAML/JSON provisioning; только
  env-плейсхолдеры (`${VAR}`). PRIMARY enforcement — собственный unit-тест `tests/grafana/unit`,
  который парсит YAML/JSON и проверяет, что `password`/`secureJsonData.*` начинаются с `$`
  (env-ссылка), а не plaintext: pre-commit secret-скан хука ловит только известные форматы
  токенов и generic-пароль (`changeme_...`) НЕ поймает — на него полагаться нельзя (это
  вторичный слой). Уточнение: `TRINO_PASSWORD` в environment контейнера grafana (для
  подстановки) виден через `docker inspect` — это container-env, не git; «0 plaintext» относится
  к репозиторию.
- **FR-007 Данные для демо.** `make build-gold-demo` — seed перед приёмкой (панели непусты);
  чистый `make up` без данных → панели «No data» (не ошибка) — ожидаемое состояние.
- **FR-008 Make/health.** `make grafana-smoke` (аддитивно, поверх поднятого стека) — HTTP API
  проверки; плагин-health отдельно от compose-healthcheck (тот проверяет только
  Grafana `/api/health`, не наличие плагина).
- **FR-009 Тесты.** `tests/grafana/unit/` (yaml.safe_load datasource+provider, json.load
  дашбордов: schemaVersion/title/panels, НЕТ plaintext-кредов, datasource по имени не uid) +
  `tests/grafana/integration/` (requires_stack, HTTP API кредами из env): `/api/datasources`
  (Trino есть), `/api/datasources/uid/<uid>/health` (соединение с Trino живо),
  `/api/search?type=dash-db` (оба дашборда), `/api/plugins/trino-datasource/settings`
  (enabled).
- **FR-010 Документация.** architecture.md += Dashboards: provisioning-структура, datasource,
  плагин+офлайн-риск («первый make up требует сеть для плагина»), env-правка compose (снять
  конфликт с прежней заметкой «compose не трогается»), список панелей/источников, I-8-заметка
  (Trino-down = ошибка панели, не блокер).

## Non-Functional Requirements

- **NFR-001 Подъём.** После `make up` (тёплый) datasource health = OK ≤30с (после готовности
  Trino); дашборды видны сразу из provisioning.
- **NFR-002 Изоляция (I-8).** Grafana вне пути данных: её падение/недоступность плагина не
  влияет на ingest/transform/build-gold (проверяется: остановить grafana → make smoke зелёный).
- **NFR-003 Наблюдаемость.** Оба дашборда покрывают журнал (все stage) и все три gold-витрины;
  свежесть и ошибки видны без docker logs.
- **NFR-004 Безопасность.** 0 plaintext-кредов в git; datasource только к trino:8443 внутри
  app_net; 0 новых опубликованных портов (grafana:3000 уже был в 001).
- **NFR-005 Сопровождаемость.** Дашборды как код; новая панель = правка JSON через export;
  плагин запинен по версии.
- **NFR-006 Bounded-нагрузка (I-15).** Auto-refresh дашбордов — не агрессивнее 30с (или off по
  умолчанию); каждая панель journal-источника ограничена time-range пикера + LIMIT, чтобы
  частота refresh × SQL к single-node Trino не давала растущей нагрузки по мере роста журнала.

## Authentication & Access

Grafana admin — из env (`GRAFANA_ADMIN_USER/PASSWORD`, контракт 001), порт 3000 на 127.0.0.1.
Datasource→Trino — user `loftnav`/`TRINO_PASSWORD` из env через `$__env`-подстановку (не
plaintext), HTTPS:8443 self-signed (tlsSkipVerify). Новых поверхностей доступа/портов/ролей нет
(single-user, ролей продукта нет). SSO отсутствует (устав v1.0.0).

## Out of Scope

- Алертинг (нет канала уведомлений в стеке — отдельная будущая фича).
- Новая gold-витрина качества (`mart_quarantine_summary`) — расширение frozen 004; quarantine
  через journal/information_schema.
- Множественные фильтры/роли/saved views/drill-down (single-user); максимум template variable
  district.
- Экспорт датасета (006); правки самих gold-витрин/журнала (004/002).
- Vendoring плагина в git (бинарь) — runtime GF_INSTALL_PLUGINS с пином.

## Affected Services

Изменяется: `infra/grafana/provisioning/datasources/trino.yaml`,
`infra/grafana/provisioning/dashboards/{ops.yaml,apartments.yaml,platform-ops.json,apartments.json}`,
`docker-compose.yml` (ТОЛЬКО environment сервиса grafana — аддитивно), `.env.example` (при
необходимости комментарий), `Makefile` (+grafana-smoke), `docs/architecture.md`,
`tests/grafana/**`. Не затрагивается: код платформы src/loftnav (Grafana читает только через
Trino), healthcheck/сети/volumes/порты grafana, smoke/ingestion/transform/gold-тесты (обязаны
остаться зелёными), другие сервисы compose.

## Edge Cases

Плагин не поставился (офлайн) → datasource не создан = БЛОКЕР (документируется требование сети
на первый up); Trino down → ошибка панели = НЕ блокер (I-8; browser-QA не заводит тикет);
пустые витрины/журнал до build-gold-demo → «No data», не ошибка; self-signed TLS без
tlsSkipVerify → handshake fail (маскирует «Trino не работает») — tlsSkipVerify обязателен;
пароль в git → secret-скан + unit-тест ловят; 0 quarantine-таблиц → панель показывает пусто, не
падает; time-range на atemporal gold → панели без time-picker; datasource по uid вместо имени →
«Datasource not found» на чистой машине (FR-005 запрещает).

## Assumptions

- Стек 001-004 живёт; grafana и trino в app_net (подтверждено compose); build-gold-demo
  прогнан для данных.
- Плагин `trino-datasource` совместим с Grafana 12.3.8, синтаксис `$__env{}` и точные auth-поля
  — spike первой задачей (методология 002-004); при несовместимости — план-ревизия.
- Первый `make up` на чистом volume требует интернет для скачивания плагина (кешируется в
  grafana_data далее).

## Success Criteria

1. Чистый `make up` + `make build-gold-demo` → Grafana (127.0.0.1:3000) показывает
   Trino-datasource (health OK) и оба дашборда из provisioning, без ручной настройки.
2. Дашборд «Операции»: статус/свежесть/quarantine/ошибки из pipeline_runs видны и корректны.
3. Дашборд «Квартиры»: три gold-витрины рендерятся живыми данными; is_small_sample виден;
   фильтр district работает.
4. `grafana-smoke` (HTTP API): datasource health OK, оба дашборда найдены, плагин enabled.
5. Grafana остановлена → `make smoke`/пайплайны зелёные (I-8); 0 plaintext-кредов в git.
6. `pytest -q && ruff check .` зелёные (001-005 + tests/grafana/unit); browser-QA
   (renata/semiglazka) проходит оба дашборда без блокеров; secret-скан зелёный.
