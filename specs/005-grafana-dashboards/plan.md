# Plan 005 — grafana-dashboards

Вход: `spec.md` (после правок аудита). Отчёт: `reviews/stage-2-audit.md`.

## Technical Approach

Provisioning-файлы (datasource YAML + два дашборда JSON + provider'ы) в
`infra/grafana/provisioning/`; аддитивная правка env grafana в compose (плагин + креды);
дашборды как код; тесты — unit (структура/секреты) + integration (HTTP API) + browser-QA.
Всё поднимается при `make up`. Техрешения:

- **T1. Spike первой задачей** [CRITICAL #2/#18/#19, FR-001/FR-002]: на живом
  `grafana/grafana:12.3.8` поставить `trino-datasource`, эмпирически определить:
  (а) точную форму env-подстановки (`$VAR` vs `${VAR}`) в provisioning; (б) точные auth-поля
  плагина для basic (`jsonData.user` / `basicAuthUser` / `secureJsonData.*`); (в) реальный
  `/api/datasources/uid/<uid>/health` = OK против trino:8443. Результат → architecture.md.
- **T2. Datasource YAML** [FR-001, FR-006]: type trino-datasource, url https://trino:8443,
  tlsSkipVerify, `${TRINO_PASSWORD}`/`${TRINO_USER}` (форма — по spike), editable:false.
- **T3. compose env (аддитивно)** [FR-002, ARCH #12/#13]: в environment grafana добавить
  `GF_INSTALL_PLUGINS=trino-datasource@<пин из spike>`,
  `GF_PLUGINS_ALLOW_LOADING_UNSIGNED_PLUGINS=trino-datasource`, `TRINO_USER`, `TRINO_PASSWORD`.
  Healthcheck/networks/volumes/ports НЕ трогать. Обновить architecture.md §15 (снять «compose
  не трогает» → факт аддитивной env-правки).
- **T4. Дашборд «Операции»** [FR-003, CRITICAL #3 I-15]: platform-ops.json + ops.yaml provider.
  КАЖДАЯ панель journal-источника bounded: failed/лента — `WHERE started_at >= $__timeFrom()`
  + `LIMIT 200`; агрегаты (accepted/rejected, свежесть) — `WHERE started_at BETWEEN
  $__timeFrom() AND $__timeTo()`. quarantine-обзор — information_schema (дёшев). Никакого
  `SELECT * FROM pipeline_runs` без bound. unit-тест: в SQL каждой панели есть LIMIT или
  time-filter.
- **T5. Дашборд «Квартиры»** [FR-004, WARNING #5]: apartments.json + apartments.yaml.
  district/style — atemporal (per-panel time override, НЕ dashboard-level); listing_dynamics —
  time-picker по load_date. Template variable district. is_small_sample виден.
- **T6. datasource по имени/${DS_TRINO}** [FR-005, ARCH #15]: JSON ссылается на datasource
  через templating input `${DS_TRINO}`, не hardcoded uid; unit-тест проверяет ВСЕ ссылки
  (panels targets + templating + annotations), не одну.
- **T7. auto-refresh off** [WARNING #4, NFR-006]: `refresh: ""` (или ≥5м) в обоих JSON;
  unit-тест на поле refresh.
- **T8. Секреты — primary unit-тест** [CRITICAL #1, FR-006]: `tests/grafana/unit` парсит
  YAML/JSON и требует `password`/`secureJsonData.*` начинаться с `$`; НЕ полагаться на
  secret-скан хука (generic-пароль не ловится). Хук — вторичный слой.
- **T9. Тесты** [FR-009]: unit (yaml.safe_load datasource/provider, json.load дашбордов:
  schemaVersion/title/panels/refresh, secret-check T8, datasource-by-name T6, bounded-SQL T4) +
  integration requires_stack (HTTP API кредами из env: /api/datasources, health, search
  dash-db, /api/plugins/trino-datasource/settings enabled).
- **T10. Make/health** [FR-008]: `make grafana-smoke` (аддитивно, поверх up); плагин-health
  через /api/plugins endpoint отдельно от compose-healthcheck.
- **T11. Документация/decision records** [FR-010, WARNING #8, INFO #16/#17]: architecture.md +=
  Dashboards; decision record unsigned-плагин (accepted risk, пин версии — единственный барьер,
  integrity-checksum отсутствует); сетевая гарантия I-4 (grafana НЕ в data_net — физически нет
  пути к MinIO); разграничить «AGENTS.md generated-дашборды» ≠ «Grafana provisioning JSON»;
  офлайн-риск плагина; env-правка compose.
- **T12. browser-QA** [FR-009, Success #6]: renata/semiglazka открывают 127.0.0.1:3000 кредами
  из .env, проходят оба дашборда после build-gold-demo; Trino-down = ошибка панели НЕ блокер
  (I-8), datasource-не-создан/пароль-в-git/плагин-не-встал = блокеры.

## Units of Work

- **u1-spike-datasource** — spike (T1), datasource YAML (T2), compose env (T3) [FR-001, FR-002]
- **u2-dashboards** — оба JSON + provider'ы, bounded SQL, time-override, refresh-off,
  datasource-by-name (T4-T7) [FR-003, FR-004, FR-005]
- **u3-tests-make** — unit (secret/bounded/refresh/by-name) + integration HTTP API +
  grafana-smoke (T8-T10) [FR-006, FR-008, FR-009]
- **u4-docs-qa** — architecture.md + decision records, browser-QA (T11/T12) [FR-007, FR-010]

## Implementation Steps

1. Spike (T1) → зафиксировать env-форму, auth-поля, версию плагина, health OK.
2. u1 → datasource + compose env; grafana поднимается, datasource health OK.
3. u2-dashboards → оба дашборда видны, bounded, панели рендерят данные (после build-gold-demo).
4. u3-tests-make → unit+integration зелёные, grafana-smoke.
5. u4 → architecture.md + browser-QA renata/semiglazka; полный pytest+ruff+smoke (001-005).

## Files to Create/Modify

Создаются: `infra/grafana/provisioning/datasources/trino.yaml`,
`infra/grafana/provisioning/dashboards/{ops.yaml,apartments.yaml,platform-ops.json,apartments.json}`,
`tests/grafana/{unit,integration}/**`. Изменяются: `docker-compose.yml` (ТОЛЬКО environment
grafana), `Makefile` (+grafana-smoke), `docs/architecture.md`, `.env.example` (комментарий если
нужно). Не трогаются: src/loftnav (Grafana не в пути данных), healthcheck/сети/volumes/порты
grafana, тесты 001-004.

## Known Risks

1. Плагин/синтаксис/auth — не подтверждены докой (CRIT #2, WARN #18/#19); закрываются spike T1
   до массового кода; при несовместимости с 12.3.8 — план-ревизия.
2. **I-7 SHOULD-FLAG устава: unsigned-плагин** trino-datasource исполняется в контейнере grafana
   с доступом в app_net; integrity — только пин версии, checksum отсутствует. Осознанный риск
   локального MVP; decision record в architecture.md (T11); паттерн соответствует практике
   апстрима Trino. Ратифицируется владельцем через approve этой спеки.
3. Secret-скан хука не ловит generic-пароль (CRIT #1) → primary enforcement — unit-тест T8.
4. Офлайн-первый-up (плагин из сети) — control-plane egress ПО, не data (I-1 PASS);
   документируется.
5. Full-scan журнала на refresh (CRIT #3/WARN #4) — закрыт bounded-SQL T4 + refresh-off T7.

## Traceability

FR-001→T1/T2/u1 · FR-002→T3/u1 · FR-003→T4/u2 · FR-004→T5/u2 · FR-005→T6/u2 · FR-006→T8/u3 ·
FR-007→T12/u4 · FR-008→T10/u3 · FR-009→T9/u3 · FR-010→T11/u4 · NFR-001→T1/шаг2 · NFR-002→T12 ·
NFR-003→T4/T5 · NFR-004→T2/T8 · NFR-005→T6 · NFR-006→T4/T7.
