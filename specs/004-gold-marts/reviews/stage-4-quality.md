# Stage 4 — Quality, отчёт (004-gold-marts)

Дата: 2026-07-20. Состав (делегированный): адверсарный QA Verifier + QA Director. Матрица —
requirements-matrix.md.

## Единственный проход → PASS (без фикс-цикла)

Адверсарно подтверждено (CRITICAL 0, WARNING 0): целостность балансов витрин против silver
(SUM=11=COUNT); is_loft все NULL + отсутствие style-эвристики в коде (I-11 anti-leakage);
защита от деления на ноль (area=0 → NULL, не Infinity/ошибка); атомарность CREATE OR REPLACE
под параллельным чтением (6 потоков, 0 TABLE_NOT_FOUND); malformed --only → читаемая ошибка;
orphan-cleanup не задевает decoy-таблицы (startswith, не LIKE); детерминизм — дамп витрин
побайтово идентичен на 2 прогонах; журнал stage=build_gold не путает anti-join transform.

Код-ревью чист: SELECT * нет, идентификаторы через ident + snapshots_relation ($snapshots вне
санитайзера), значения bind, approx_percentile через CAST DOUBLE, явные CAST DECIMAL(p,s),
run_id regex, SHOW TABLES+startswith, 0 TODO, комментарии=коду.

## 3 INFO → бэклог (не блокируют)

1. `_computed_at` — timestamp with tz (дефолт Trino), spec называет TIMESTAMP; тип стабилен, но
   decision record если 005/006 tz-чувствительны.
2. Локальный импорт quote_ident в features.py (стиль, не функциональность).
3. Ветка cleanup __build_/__old_ недостижима при CREATE OR REPLACE (defensive dead-code,
   задокументирована — не удалять без проверки истории).

## Вердикт: **PASS** (retry 0)

Основание: матрица 27/27 DONE; адверсарный проход CRITICAL/WARNING 0; тесты 98 passed, ruff
clean, smoke 4 passed; балансы/детерминизм/атомарность/anti-leakage подтверждены независимо.

## Хвосты → бэклог

is_loft/006 координация (unlabeled feature-датасет, разметка вне платформы); cross-source дубли
инфлируют count; approx-медиана; full-scan features (PERF-4); 3 INFO выше. Все документированы.
