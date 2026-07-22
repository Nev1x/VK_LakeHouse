# Requirements Matrix — 007-loft-markers (stage-4)

Источник: адверсарный QA Verifier (проход 1, PASS без фикс-цикла) + независимая верификация
QA Director. Против текущего spec.md.

| ID | Статус | Evidence |
|---|---|---|
| FR-001 | DONE | ALTER-эволюция silver (DESCRIBE-diff→ADD COLUMN, только из _SCHEMA — адверсарно: инъекция в имени bronze-колонки НЕ попала в silver-схему; идемпотентность ensure подтверждена повтором) |
| FR-002 | DONE | MAPPABLE_FIELDS+3; sanity адверсарно: 0.5/12.0/1700/2150 → quarantine с причинами, границы 1.5/10.0/1800/2100 инклюзивно проходят |
| FR-003 | DONE | 3 .toml дополнены после DESCRIBE-подтверждения имён; reprocess ×3 по штатному протоколу (журнал: 3 цикла, все success) |
| FR-004 | DONE | features 26 колонок (маркеры перед is_loft, _computed_at последняя — DESCRIBE подтверждает); обе версии =2; манифест v2 |
| FR-005 | DONE | +3 гварда ALTER, +тест 26 колонок, +loft-markers integration; полный pytest 144 passed ×2 (до/после адверсарной нагрузки) |
| FR-006 | DONE | architecture.md: gap-004 снят, схемы v2, раздел 007, root-cause запись медианы |
| NFR-001 | DONE | полный цикл 80.5с (≤300с, запас ×3.7); build-gold 8.8с |
| NFR-002 | DONE | v035 (v1/23 колонки) sha manifest+parquet идентичны до/после нового экспорта; v075 (v2/26) читается pandas независимо |
| NFR-003 | DONE | 0 новых зависимостей/портов; тесты 001-006 зелёные (144 passed целиком) |
| SC-1 | DONE | silver 6050: маркеры заполнены у 3000+3000, NULL wall_material у lite (SELECT, двойная проверка) |
| SC-2 | DONE | features 6050×26; export v2, pandas 26 колонок; спот-чек 3 id — значения parquet == silver |
| SC-3 | DONE | старые версии нетронуты (sha факт, не дата) |
| SC-4 | DONE | pytest 144 passed БЕЗ deselect; ruff clean; smoke 4 passed |

**Вложенный багфикс 004 (медиана):** root cause доказан (approx_percentile недетерминирован на
группах 400+; репро kulibin 5/5 + Tech Lead 3/3); фикс — точная медиана (предодобренный
fallback плана 004 T3); детерминизм витрин ×5 идентичен; ручная сверка чётной (528) и нечётной
с различными центральными (510) групп сошлась; guard «нет approx_percentile»; тайминг не
деградировал.

**Итог: DONE 13 / PARTIAL 0 / MISSING 0** + багфикс верифицирован. CRITICAL 0 | WARNING 0 |
INFO 1 (orphan quarantine-таблицы прежних QA-сессий — уборка отдельно).
