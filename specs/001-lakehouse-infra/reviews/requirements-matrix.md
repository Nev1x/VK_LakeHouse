# Requirements Matrix — 001-lakehouse-infra (stage-4)

Источник: Requirements Validator (первый проход stage-4, 27/27) + переверификация после
fix-цикла (Tech Lead/QA Director, второй проход). Оценка против текущего текста spec.md
(вкл. stage-3-уточнение FR-015).

| ID | Статус | Evidence |
|---|---|---|
| FR-001 | DONE | compose: 5 сервисов, точные теги (trino:483, postgres:16.14-alpine3.23, minio/mc RELEASE.2025-*, grafana:12.3.8), container_name loftnav-*; 0 «:latest» |
| FR-002 | DONE | 3 сети loftnav_{public,app,data}_net; членство: grafana=public+app, trino=app+data, minio/postgres/minio-init=data |
| FR-003 | DONE | публикации только 127.0.0.1:{3000,8080,9000,9001} (host 8080→container 8443); Postgres без ports; перечень ратифицирован владельцем (Approve, state.md) |
| FR-004 | DONE | iceberg.properties: type=jdbc, warehouse s3://warehouse/, connection-url без userinfo, креды ${ENV:...} |
| FR-005 | DONE | minio-init: mc mb --ignore-existing (raw/warehouse/ml-datasets); trino ждёт service_completed_successfully |
| FR-006 | DONE | MEDALLION_NAMESPACES=(bronze,silver,gold,quarantine), идемпотентный bootstrap; smoke в iceberg.smoke |
| FR-007 | DONE | healthchecks-liveness у 100% сервисов, depends_on healthy/completed, trino start_period 90s |
| FR-008 | DONE | .env.example — раздельные переменные/плейсхолдеры; .gitignore .env*/!example/override; make up без .env — читаемая ошибка |
| FR-009 | DONE | Makefile .POSIX: up/down(без -v)/smoke/ps/logs; BSD-совместим (нет sed -i/flock/GNU-специфики) |
| FR-010 | DONE | smoke: data-plane liveness (блокирующий) + grafana non-blocking (fix I-8) + round-trip со сравнением значений + cleanup + негативный env-тест; 4 passed |
| FR-011 | DONE | pyproject: src-layout, testpaths=["tests"], ruff extend-exclude харнеса; pytest -q && ruff check . зелёные |
| FR-012 | DONE | jvm.config -Xmx1792m; mem_limit: trino 2816m/pg 768m/minio 1024m/grafana 512m/init 128m (Σ≈5.1GB≤6GB) |
| FR-013 | DONE | architecture.md as-built (+quickstart, TLS-note, internal-DNS, quarantine, OOM-runbook, down -v warning, заметки loader/I-4) |
| FR-014 | DONE | grafana контейнер+healthcheck+env-креды, provisioning-каталоги пустые (005) |
| FR-015 | DONE | password-auth file/bcrypt; dual-port: internal HTTP:8080 не публикуется, публикуемый HTTPS:8443; 401 без кредов / 200 с кредами / plain-HTTP отвергается (проверено curl) |
| NFR-001 | DONE | замеры (2026-07-20): тёплый up 34–50с ≤120с; smoke ≤9с wall ≤90с; таймаут per-check 30с |
| NFR-002 | DONE | Σ лимитов ≈5.1GB ≤6GB, heap 1792m ≤2GB, VM-требования в architecture.md |
| NFR-003 | DONE | именованные volumes; down без -v; цикл down→up→smoke зелёный + реальная строка пережила рестарт (stage-3) |
| NFR-004 | DONE | healthcheck 100%, make ps, читаемые assert'ы smoke, json-file 10m×10 на всех сервисах |
| NFR-005 | DONE | 0 публикаций 0.0.0.0, 0 userinfo-URL, 0 дефолт-кредов (grep/compose config); secret-скан хука прошёл на коммитах |
| NFR-006 | DONE | пины точные, порты/креды через .env, arm64-манифесты подтверждены docker manifest inspect, TZ фиксирован |
| SC-1 | DONE | make up с нуля → 4/4 healthy (stage-3; текущее состояние healthy подтверждено обоими проходами stage-4) |
| SC-2 | DONE | smoke ×2 идемпотентно; down→up→smoke зелёный (stage-3, независимый повтор Test Engineer первого прохода) |
| SC-3 | DONE | compose config: только перечень FR-003 на 127.0.0.1, PG не опубликован |
| SC-4 | DONE | pytest 4 passed, ruff clean (переподтверждено после фикса) |
| SC-5 | DONE | architecture.md построчно сверен с фактом (Tech Writer: 0 расхождений; gaps закрыты fix-циклом) |
| SC-6 | DONE | secret-скан зелёный (в т.ч. поймал и заставил перефразировать literal-паттерн в отчёте stage-1 — работает) |

**Итог: DONE 27 / PARTIAL 0 / MISSING 0.**
