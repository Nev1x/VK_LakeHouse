# Requirements Matrix — 005-grafana-dashboards (stage-4)

Источник: адверсарный API/JSON QA (проход 1, PASS+1 WARNING) + browser-QA gap + верификация
фикса (проход 2, QA Director). Против текущего spec.md.

| ID | Статус | Evidence |
|---|---|---|
| FR-001 | DONE | trino.yaml: type trino-datasource, https://trino:8443, tlsSkipVerify, basicAuth+basicAuthUser ${TRINO_USER}, secureJsonData.basicAuthPassword ${TRINO_PASSWORD}, editable:false; spike подтвердил health OK |
| FR-002 | DONE | compose env grafana аддитивно (GF_PLUGINS_PREINSTALL_SYNC@1.0.11 c GitHub — grafana.com 451, GF_INSTALL_PLUGINS deprecated; ALLOW_UNSIGNED; TRINO_USER/PASSWORD); healthcheck/сети/volumes/порты не тронуты (diff подтверждён) |
| FR-003 | DONE | platform-ops.json: 5 панелей из pipeline_runs, ВСЕ bounded ($__timeFrom/$__timeTo + LIMIT 200 для failed); quarantine через information_schema |
| FR-004 | DONE | apartments.json: 3 gold-панели; district/style atemporal, listing_dynamics WHERE load_date BETWEEN; template variable district (:singlequote — нейтрализует инъекцию в значении, адверсарно) |
| FR-005 | DONE | JSON внутри provisioning/dashboards/; datasource по ${DS_TRINO} (не hardcoded uid) во всех targets/templating (адверсарно проверено) |
| FR-006 | DONE | 0 plaintext-паролей в git (только ${VAR}); PRIMARY unit-тест на env-ссылки; container-env пароль — не git (документировано) |
| FR-007 | DONE | build-gold-demo seed; чистый up без данных → No data (не ошибка) |
| FR-008 | DONE | make grafana-smoke (HTTP API); плагин-health на надёжном сигнале (агрегатный /api/plugins enabled=true + health OK, не квирк /settings — фикс) |
| FR-009 | DONE | tests/grafana unit (secret/bounded/by-name/refresh) + integration (datasources/health/search/plugins-enabled на надёжном сигнале); 16 passed |
| FR-010 | DONE | architecture.md §Dashboards + spike-таблица + decision records (unsigned снят — плагин подписан; I-4 grafana не в data_net; офлайн-риск; browser-QA gap) |
| NFR-001 | DONE | datasource health OK после recreate; плагин кэшируется в grafana_data |
| NFR-002 | DONE | I-8 адверсарно: docker stop grafana → make smoke зелёный (non-blocking warning) → start healthy |
| NFR-003 | DONE | оба дашборда покрывают все stage журнала + 3 gold-витрины; свежесть/ошибки без docker logs |
| NFR-004 | DONE | 0 plaintext-кредов в git; datasource только trino:8443 в app_net; 0 новых портов; grafana не в data_net (сетевая гарантия) |
| NFR-005 | DONE | дашборды как код; плагин запинен 1.0.11; datasource-by-name |
| NFR-006 | DONE | refresh:"" в обоих JSON; панели журнала bounded time+LIMIT (адверсарно) |
| SC-1 | DONE | build-gold-demo → datasource health OK, оба дашборда из provisioning (grafana-smoke) |
| SC-2 | DONE | Операции: статус/свежесть/quarantine/ошибки из pipeline_runs (ds/query возвращает реальные данные) |
| SC-3 | DONE | Квартиры: 3 витрины через ds/query (районы с ценами); is_small_sample в SQL; district фильтр |
| SC-4 | DONE | grafana-smoke: datasource health OK, оба дашборда найдены, плагин enabled (надёжный сигнал) |
| SC-5 | DONE | grafana остановлена → smoke зелёный (I-8); 0 plaintext-кредов git |
| SC-6 | PARTIAL | pytest 114 passed (001-005 + tests/grafana); ruff clean; secret-скан 0. Browser-QA (renata/semiglazka) — GAP: Playwright MCP не подключён в runtime; визуальный проход не выполнен, покрытие через API/JSON + health + ds/query рендер (честный gap, принцип 4) |

**Итог: DONE 26 / PARTIAL 1 (SC-6 browser-часть, среда без браузера) / MISSING 0.** CRITICAL 0;
1 WARNING (тест плагина) закрыт фикс-циклом; browser-QA — documented environmental gap.
