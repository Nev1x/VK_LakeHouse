# Stage 2 — Audit Team, отчёт (001-lakehouse-infra)

Дата: 2026-07-19. Состав: Security Reviewer, Performance/Resources Analyst, Architecture
Reviewer, Compatibility Reviewer, Constitution Gate (5 параллельных субагентов) + повторный
Constitution Gate после правок спеки. Директор: Audit Director (основная сессия).

## Сводка находок (по ревьюерам, до правок)

| Ревьюер | CRITICAL | WARNING | INFO |
|---|---|---|---|
| Security | 1 (SEC-1 Trino без auth: blind CSRF → произвольный SQL) | 1 (.gitignore не покрывал .env*/override) | 2 |
| Performance | 2 (C1 include-coordinator обязателен; C2 mem_limit==Xmx → OOM-kill) | 8 | 5 |
| Architecture | 1 (F2 quarantine-контракт не зарезервирован → 002/003 разойдутся) | 4 | 4 |
| Compatibility | 0 | 3 (пины/имена свойств сверять с доками релиза) | 3 |
| **Итого** | **4** | **16** | **14** |

## Constitution Check

- Прогон 1 (исходная спека): MUST-FLAG 2 (I-1: публикация data_net-портов + противоречие
  FR-003 vs SC-3; I-7: Trino UI без пароля) · SHOULD-FLAG 0 · NEEDS-INFO 3 (I-9 retention,
  I-10 откат, I-11 Grafana-решение).
- Правки спеки: FR-015 (Trino password-auth), FR-006 (+`iceberg.quarantine` контракт), FR-003 и
  SC-3 согласованы (исчерпывающий перечень loopback-портов), NFR-004 (+ротация логов
  json-file 10m×10), секция Rollback, FR-014 переведён в решённое KEEP, FR-008 (.gitignore
  .env*/override), FR-011 (testpaths/extend-exclude), FR-013 (+internal-DNS контракт,
  OOM-runbook, заметки loader/I-4), Auth & Access (+MVP-риск общих MinIO-кредов + guardrail).
- Прогон 2 (после правок): **MUST-FLAG: 0 · SHOULD-FLAG: 0 · NEEDS-INFO: 0**. Условие: перечень
  портов 3000/8080/9000/9001 предъявляется владельцу явным пунктом на approval-гейте
  (Approve = решение владельца по I-1).

## Закрытие CRITICAL

- SEC-1 → FR-015 (password-file auth + allow-insecure-over-http на loopback) + план T6.
- C1 → план T1 (`node-scheduler.include-coordinator=true` — non-negotiable строка).
- C2 → план T2 (mem_limit trino 2816m > Xmx 1792m; полная таблица лимитов).
- F2 → FR-006 (`iceberg.quarantine`, таблицы `<слой>_<источник>_rejects`, реализация в 002/003).

## WARNING → куда попали

Все 16 WARNING адресованы: perf-значения (W1–W8) → план T1/T2/T7/T8/T9 + Known Risks 2–3;
compat (пины/свойства/native-s3) → план T3/T4/T5 + шаг 1 + Known Risks 1; architecture
(F1 loader-сеть, F5 internal hostname, F6 testpaths, F7 MinIO-креды) → FR-013/FR-011/Auth-секция
+ Known Risks 5; SEC-3 (.gitignore) → FR-008.

## Механические сигналы (прогнаны в этой сессии)

spec-lint: OK (10/10 секций). plan-lint: OK — REQUIRED-секции на месте, traceability 21/21
(FR-001…FR-015, NFR-001…NFR-006 адресованы), coherence 0 overreach, 0 warn.

## Вердикт аудита

Спека и план готовы к approval-гейту. Пункты, требующие явного решения владельца на гейте:
(1) ратификация перечня loopback-портов 3000/8080/9000/9001 (I-1); (2) FR-014 Grafana в 001
(KEEP, альтернатива — Revise).
