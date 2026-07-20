# Stage 4 — Quality, отчёт (006-ml-dataset-export)

Дата: 2026-07-20. Состав (делегированный): адверсарный QA Verifier + QA Director. Матрица —
requirements-matrix.md. Финальная фича бэклога.

## Проход 1 → PASS с 1 WARNING

Адверсарно подтверждено (CRITICAL 0): immutability (старая версия побайтово цела, коллизия
fail-loud RuntimeError); независимое чтение parquet (pandas+pyarrow, 3-осевой row_count
11=11=11); integrity (sha256 файлов = манифест); S3Store allowlist (warehouse→ValueError, вкл.
адверсарные регистр/пробел/None — нет байпаса); 0-HTTP/SSRF (0 requests/urllib, monkeypatch-тест);
детерминизм (один snapshot → идентичное содержимое); пустой срез (валидная пустая версия, не
падение); конкурентность (второй export → lock-ошибка без коллизии vNNN). Код-ревью чист:
put_or_fail отдельный, allowlist в конструкторе, ParquetWriter потоковый, Decimal→строка,
манифест последним, snapshot-пин, bind, is_loft NULL, TODO 0, frozen-поля, колонки features
сверены. WARNING: унаследованный lock-текст «ingest уже идёт» вводит в заблуждение для
export/transform/build-gold.

## Fix-цикл (stage-3)

Текст ошибки общего process_lock: «ingest уже идёт» → «конвейер уже занят» (нейтрально для всех
стадий). Тесты не завязаны на старый текст, 133 passed. Checkpoint: fix-коммит.

## Проход 2 → верификация (QA Director лично)

pytest 133 passed после правки; ruff clean; тесты не ломаются от смены текста; diff — точечный.
Адверсарные оси прохода 1 (immutability/чтение/integrity/allowlist/0-HTTP/детерминизм/пустой/
конкурентность) фиксом текста не затронуты — evidence валиден.

## Вердикт: **PASS** (retry 1)

Основание: матрица 26/26 DONE; CRITICAL 0; WARNING закрыт; adversarial PASS по immutability,
independent-read, integrity, allowlist, 0-HTTP, детерминизму. Финальная фича замыкает пайплайн
ingest→transform→gold→dashboards→export.

## Хвосты → бэклог / владельцу

**PATCH устава I-4 (владельцу, Часть III):** ml-datasets — egress-зона вне каталога (Gate PASS);
рекомендован PATCH 1.0.0→1.0.1. Также: фото только ссылки (копии — решение владельца);
ml-datasets накопил dev-версии (immutable, ожидаемо); jsonl decimal=строка vs parquet
(в манифесте notes); INFO — parquet побайтово совпал в прогоне (не контракт).
