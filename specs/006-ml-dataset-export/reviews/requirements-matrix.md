# Requirements Matrix — 006-ml-dataset-export (stage-4)

Источник: адверсарный QA Verifier (проход 1, PASS+1 WARNING) + верификация фикса (проход 2, QA
Director). Против текущего spec.md.

| ID | Статус | Evidence |
|---|---|---|
| FR-001 | DONE | cli export-dataset --format; занятый lock → читаемая ошибка (нейтральный текст после фикса) |
| FR-002 | DONE | FOR VERSION AS OF snapshot ORDER BY id, fetchmany(5000); snapshots_relation переиспользован; is_loft null_count агрегатом |
| FR-003 | DONE | parquet (pyarrow ParquetWriter потоковый) + jsonl (Decimal→строка, timestamp ISO); --format |
| FR-004 | DONE | S3Store bucket-параметр конструктора + allowlist {raw,ml-datasets} (warehouse→ValueError, адверсарно вкл. регистр/пробел/None); put_or_fail отдельный; list_prefixes CommonPrefixes+пагинация; I-4 read через Trino |
| FR-005 | DONE | list max+1 (пустой→v001, строгий regex); immutability адверсарно: старая версия побайтово цела, коллизия put_or_fail fail-loud (RuntimeError) |
| FR-006 | DONE | data-файлы первыми, manifest последним; частичный сбой → версия без манифеста невалидна |
| FR-007 | DONE | манифест 14 frozen-полей + notes (additive); created_at datetime.now(UTC); sha256 из инкремента; target_populated:false; photo_handling:links |
| FR-008 | DONE | детерминизм адверсарно: один snapshot → идентичное содержимое (content-sha jsonl), тот же source_snapshot_id |
| FR-009 | DONE | photo_urls passthrough; 0 requests/urllib в export-коде; тест test_zero_external_http (monkeypatch socket) passed |
| FR-010 | DONE | пустой срез адверсарно (WHERE 1=0): success rows_ok=0, warn, валидная пустая версия row_count=0, не падение |
| FR-011 | DONE | общий pipeline-lock; конкурентный export адверсарно → второй читаемая lock-ошибка, без коллизии vNNN |
| FR-012 | DONE | журнал stage='export' snapshot_id/rows_ok try/finally; anti-join transform не сломан (make transform 0 партий) |
| FR-013 | DONE | pyarrow 25.0.0 пин; S3Store расширен не дублирован; jsonl/manifest stdlib |
| FR-014 | DONE | make export-dataset(-demo); 19 export-тестов; parquet читается pandas+pyarrow независимо (3-осевой row_count) |
| FR-015 | DONE | architecture.md §Export (раскладка, манифест frozen, I-4 egress-трактовка, детерминизм, фото/SSRF, fail-loud, порядок записи) |
| NFR-001 | DONE | export ≤6с, демо-цепочка 19с (≤30с); потоковый ParquetWriter (bounded, не fetchall/не to_parquet) |
| NFR-002 | DONE | сбой → версия без манифеста невалидна; журнал failed; повтор → следующая валидная версия |
| NFR-003 | DONE | 100% экспортов в журнале snapshot_id; sha256 файлов = independent integrity (адверсарно совпал) |
| NFR-004 | DONE | данные не покидают машину; 0 исходящих HTTP (тест); креды env; 0 новых портов |
| NFR-005 | DONE | 1 новая зависимость pyarrow; S3Store расширен; манифест frozen additive |
| SC-1 | DONE | export-dataset-demo: datasets/vNNN/ manifest+parquet+jsonl; parquet pandas независимо; row_count 11=11 |
| SC-2 | DONE | повтор → v++; старая цела; перезапись → явная ошибка (адверсарно) |
| SC-3 | DONE | манифест: snapshot_id реальный, sha256 совпадает, target_populated=false, photo_handling=links |
| SC-4 | DONE | детерминизм: два экспорта на snapshot → идентичное содержимое |
| SC-5 | DONE | журнал stage='export' snapshot_id/rows_ok; виден в дашборде 005 |
| SC-6 | DONE | pytest 133 passed (001-006); ruff clean; smoke зелёный; secret-скан 0; 0 исходящих HTTP |

**Итог: DONE 26 / PARTIAL 0 / MISSING 0** (15 FR + 5 NFR + 6 SC). CRITICAL 0; WARNING (lock-текст)
закрыт фикс-циклом; INFO (parquet побайтово совпал — не контракт) — без действий.
