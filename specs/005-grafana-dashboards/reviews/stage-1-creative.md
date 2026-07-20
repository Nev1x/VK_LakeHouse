# Stage 1 — Creative Team, отчёт (005-grafana-dashboards)

Дата: 2026-07-20. Состав (делегированный): Creative Analyst + System Analyst.

## Решения
1. Плагин trino-datasource (Trino community, unsigned) — id/подпись подтверждены System Analyst
   внешне; GF_INSTALL_PLUGINS+ALLOW_UNSIGNED, пин версии; офлайн-риск документируется.
2. Два раздельных дашборда (буквальное прочтение intent, не YAGNI-объединение).
3. Панели «Операции» из pipeline_runs НАПРЯМУЮ (не через новую витрину — 004 её не строила).
4. Quarantine БЕЗ хардкода: основная метрика — pipeline_runs.rows_quarantined (architecture стр.
   306 прямо называет это входом дашборда); список reject-таблиц — information_schema; чтение
   строк reject не нужно.
5. JSON дашбордов ВНУТРИ provisioning/dashboards (единственный смонтированный путь — критично).
6. Секреты — только $__env-подстановка, secureJsonData; datasource по имени/${DS_TRINO}, не uid.
7. Аддитивная правка compose env grafana (конфликт с прежней заметкой architecture «compose не
   трогается» — снять на stage-2/3; здоровье/сети/volumes/порты не меняются).
8. КЛЮЧЕВОЕ разграничение блокеров (Creative Analyst): Trino-down = ошибка панели = НЕ блокер
   (I-8); плагин-не-встал / пароль-в-git / datasource-не-создан = блокеры.
9. CUT (YAGNI): алертинг, дашборд качества отдельно, mart_quarantine_summary, роли/мультифильтры.

## Риски (10) отражены в FR/Edge Cases
офлайн-плагин, Trino-down (не блокер), пустые данные (No data), self-signed TLS, пароль в git,
0 quarantine-таблиц, atemporal time-range, datasource-uid vs имя, Grafana 12.3.8 синтаксис.
