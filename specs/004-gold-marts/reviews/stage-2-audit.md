# Stage 2 — Audit, отчёт (004-gold-marts)

Дата: 2026-07-20. Состав: Tech Audit Reviewer + Constitution Gate (делегированный режим).

## Сводка
Tech Audit: CRITICAL 2 | WARNING 5 | INFO 8. Constitution: MUST-FLAG 0 · SHOULD 3 ·
NEEDS-INFO 0 (I-2/I-11/I-13 разобраны по существу — is_loft=NULL признан честной заготовкой,
area=0 self-verify корректен).

## CRITICAL → план
#1 ($snapshots vs строгий ident.py — sanitize отклонит/испортит `$`) → T2 отдельный
snapshots_relation() вне санитайзера; #2 (approx_percentile не принимает DECIMAL) → T3
CAST AS DOUBLE + spike. Оба — в обязательный spike T1.

## WARNING → план
run_id-валидация regex перед склейкой (#3) → T6; cleanup через SHOW TABLES+startswith не LIKE
(#4) → T7; детерминизм percentile (#5) → T1/Known Risk 2; explicit DECIMAL(p,s) агрегатов (#6)
→ T4; is_loft/006 cross-spec (#7) → decision record architecture.md/Known Risk 4.

## SHOULD устава → план (Known Risks/T12)
time-travel в пределах генерации таблицы (#1); fv2=format_version=2 пояснить (#2); явный
откат (#3).

## Механические сигналы (в сессии)
spec-lint OK 10/10; plan-lint OK — traceability 19/19, coherence 0 overreach.

## Гейт
Constitution MUST-FLAG 0 (SHOULD в план). Approve — по делегации владельца (2026-07-20).
