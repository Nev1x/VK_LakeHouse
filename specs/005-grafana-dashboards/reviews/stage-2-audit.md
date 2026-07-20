# Stage 2 — Audit, отчёт (005-grafana-dashboards)

Дата: 2026-07-20. Состав: Tech Audit Reviewer + Constitution Gate (делегированный режим).

## Сводка
Tech Audit: CRITICAL 3 | WARNING 6 | INFO 12. Constitution прогон 1: MUST-FLAG 1 (I-15) ·
SHOULD 1 (I-7 unsigned). После правок прогон 2: MUST-FLAG 0 · SHOULD 1 · NEEDS-INFO 0.

## CRITICAL → правки спеки/план
#1 secret-скан хука не ловит generic-пароль → FR-006 PRIMARY unit-тест на env-ссылки (не хук);
#2 синтаксис env `${VAR}` не `$__env{}` → FR-001 исправлен + spike подтверждает на 12.3.8;
#3 I-15 bounding панелей журнала → FR-003 bounded-выборки на всех панелях + NFR-006.

## WARNING → план
auto-refresh off/≥5м (#4) → T7/NFR-006; per-panel time override district vs listing_dynamics
(#5) → T5; unsigned-плагин decision record (#8) → Known Risk 2; spike на реальном 12.3.8 +
health OK критерий (#18/#19) → T1.

## SHOULD устава (I-7 unsigned-плагин)
Accepted-risk, decision record architecture.md, пин версии единственный барьер (checksum нет),
паттерн апстрима Trino; ратификация владельцем через approve. Не блокирует (gate-правило).

## Механические сигналы (в сессии)
spec-lint OK 10/10; plan-lint OK — traceability 16/16, coherence 0 overreach.

## Гейт
Constitution после правок MUST-FLAG 0 (I-15 закрыт), SHOULD 1 (в Known Risks). Approve — по
делегации владельца (2026-07-20), включает ратификацию unsigned-плагина.
