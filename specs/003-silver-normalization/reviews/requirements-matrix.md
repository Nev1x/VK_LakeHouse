# Requirements Matrix — 003-silver-normalization (stage-4)

Источник: адверсарный QA Verifier (проход 1) + верификация фикс-цикла (проход 2, QA Director
лично). Против текущего spec.md.

| ID | Статус | Evidence |
|---|---|---|
| FR-001 | DONE | сабкоманда transform в cli, --source/--reprocess (reprocess сужен до одного источника фикс-циклом) |
| FR-002 | DONE | configs/mapping/*.toml (tomllib rb), примитивы rename/cast/unit_convert/regex/enum_map(dict exact)/default; fail-fast валидация; regex под таймаут-watchdog |
| FR-003 | DONE | apartments_clean fv2 partitioning=ARRAY['source'], DECIMAL(12,2)/(8,2), служебные lineage-колонки; DESCRIBE подтверждает типы |
| FR-004 | DONE | Decimal str→Decimal→quantize без float (grep float=0 в transform); sanity-границы адверсарно (0→reject, 0.01→pass, 1000.01→reject) |
| FR-005 | DONE | id=sha256(len-prefix) — антиколлизия с ':' в external_id (адверсарно проверено, id уникальны) |
| FR-006 | DONE | MERGE upsert (source,external_id) с bind + партиционный предикат; last-write-wins адверсарно (старый _ingested_at не затирает новый) |
| FR-007 | DONE | anti-join stage='transform'; повтор 0 партий ≤7с |
| FR-008 | DONE | mismatch хэша конфига → стоп с подсказкой; --reprocess: DELETE партиции silver + чистка quarantine (фикс WARNING-1) + переигровка |
| FR-009 | DONE | quarantine silver-слоя через общий модуль; балансы rows_ok+rejects=источник (по прогону) |
| FR-010 | DONE | источники без конфига → journal skipped (адверсарно и в демо: apartments/flats/listings) |
| FR-011 | DONE | одна запись stage='transform' на партицию, честные счётчики; журнал сходится с фактом |
| FR-012 | DONE | единый lock ingest+transform; ReDoS-фикс гарантирует, что regex не держит lock бесконечно |
| FR-013 | DONE | ident.py, chunked_insert.py, runlog.last_status(stage) + оба call-site (ingest/transform) передают stage; регрессия 002 зелёная (CRITICAL аудита закрыт) |
| FR-014 | DONE | make transform/transform-demo; демо-конфиги t_avito/t_cian/t_domclick |
| FR-015 | DONE | 78 passed (34 transform: unit примитивы/ReDoS-time/id/инъекции + integration 3-источника/инкремент/MERGE-update/quarantine/reprocess/skip) |
| FR-016 | DONE | architecture.md += Transform (схема frozen, конфиги, инкрементальность/reprocess, I-2-трактовки, PERF-4/merge-on-read ограничения); демо-источники согласованы с фактом (INFO-1) |
| NFR-001 | DONE | transform-demo 17с (≤60с); пустой инкремент 7с (≤15с) |
| NFR-002 | DONE | честные счётчики при сбое (наследие дисциплины 002); MERGE идемпотентен по identity |
| NFR-003 | DONE | 100% партий в журнале; балансы; structured-логи с run_id |
| NFR-004 | DONE | 0 новых зависимостей (tomllib stdlib), 0 новых портов; bind+санитизация (адверсарно: инъекция в значение/external_id не сработала) |
| NFR-005 | DONE | новый источник = 1 TOML; примитив = именованная функция (не eval) |
| SC-1 | DONE | transform-demo: 3 источника в apartments_clean, DECIMAL-рубли (unit_convert тыс/руб/млн), SELECT-подтверждение |
| SC-2 | DONE | повтор 0 партий, count/содержимое стабильны |
| SC-3 | DONE | MERGE-update цены 5M→6M, count==distinct, без дубля |
| SC-4 | DONE | rejects с причинами; балансы сходятся |
| SC-5 | DONE | смена конфига → стоп с подсказкой; --reprocess переигрывает + чистит quarantine; журнал полон |
| SC-6 | DONE | pytest 78 passed (001+002+003); ruff clean; smoke 4 passed; secret-скан 0 |

**Итог: DONE 27 / PARTIAL 0 / MISSING 0** (16 FR + 5 NFR + 6 SC).
