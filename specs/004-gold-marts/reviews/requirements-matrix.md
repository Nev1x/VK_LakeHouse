# Requirements Matrix — 004-gold-marts (stage-4)

Источник: адверсарный QA Verifier (проход 1, PASS без фикс-цикла) + независимая верификация
QA Director. Против текущего spec.md.

| ID | Статус | Evidence |
|---|---|---|
| FR-001 | DONE | cli build-gold + --only; несуществующая витрина → читаемая ошибка exit 1 (адверсарно) |
| FR-002 | DONE | marts.py tuple-driven; grep SELECT * в gold = 0; unit-тест «нет *» |
| FR-003 | DONE | 3 витрины, явные CAST DECIMAL(p,s) (DESCRIBE подтверждает), NULLIF area=0, is_small_sample; баланс SUM=11=silver |
| FR-004 | DONE | apartments_features fv2; is_loft 0 non-null (адверсарно + grep нет style-эвристики); price_per_m2/floor_ratio NULL-защита; photo_urls passthrough; _silver_snapshot_id |
| FR-005 | DONE | CREATE OR REPLACE (spike: атомарен, лучше rename-swap); swap-during-read 6 потоков 0 ошибок TABLE_NOT_FOUND |
| FR-006 | DONE | полный rebuild из silver; детерминизм — дамп витрин побайтово идентичен на 2 прогонах (FOR VERSION AS OF snapshot) |
| FR-007 | DONE | lower(trim()) нормализация style/renovation; COALESCE unknown/none |
| FR-008 | DONE | журнал stage=build_gold, 4 записи/прогон, content_hash=snapshot_id, rows_ok; snapshots_relation вне ident |
| FR-009 | DONE | общий pipeline-lock |
| FR-010 | DONE | пустой silver → 0 строк без падения (адверсарно temp + test_empty_silver) |
| FR-011 | DONE | make build-gold/build-gold-demo |
| FR-012 | DONE | 98 passed (11 gold-unit + 6 gold-integration requires_stack на живом Trino) |
| FR-013 | DONE | architecture.md §Gold + §16 отклонения (CREATE OR REPLACE); SHOULD устава закрыты (time-travel/fv2/откат) |
| FR-014 | DONE | trino_client/ident/runlog/bootstrap переиспользованы; iceberg.gold в namespaces |
| NFR-001 | DONE | build-gold 9-10с (≤30с); build-gold-demo 18с |
| NFR-002 | DONE | сбой витрины не роняет остальные; CREATE OR REPLACE не оставляет битую целевую; orphan-cleanup startswith (адверсарно: decoy целы, orphan удалены) |
| NFR-003 | DONE | 100% витрин в журнале со snapshot_id; structured-логи run_id |
| NFR-004 | DONE | детерминизм на snapshot подтверждён (побайтово); approx_percentile стабилен ×5 |
| NFR-005 | DONE | 0 новых deps/портов; идентификаторы ident + snapshots_relation, значения bind; run_id regex |
| SC-1 | DONE | build-gold-demo: 3 витрины+features непусты; баланс 11=11 SELECT-подтверждён |
| SC-2 | DONE | повторный build — идентичное содержимое; swap-during-read консистентен |
| SC-3 | DONE | DESCRIBE features стабилен; is_loft все NULL; price_per_m2 NULL при area=0 |
| SC-4 | DONE | пустой silver → пустые витрины success rows_ok=0 |
| SC-5 | DONE | журнал stage=build_gold по витрине с snapshot_id и rows_ok |
| SC-6 | DONE | pytest 98 passed (001-004); ruff clean; smoke 4 passed; secret-скан 0 |

**Итог: DONE 27 / PARTIAL 0 / MISSING 0** (14 FR + 5 NFR + 6 SC). CRITICAL/WARNING адверсарного
прохода = 0; 3 INFO (tz у _computed_at, локальный импорт quote_ident, dead-code cleanup-ветка)
— косметика, в бэклог.
