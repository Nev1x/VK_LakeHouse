# Stage 3 — Dev, отчёт (006-ml-dataset-export)

Дата: 2026-07-20. Исполнитель: kulibin; Tech Lead — основная сессия. Финальная фича бэклога.

## Результат
Units u1–u4 DONE. pyarrow 25.0.0 (ParquetWriter потоковая запись по чанкам, не df.to_parquet).
CLI export-dataset: чтение features FOR VERSION AS OF snapshot ORDER BY id chunked → потоковый
parquet+jsonl+sha256 единым проходом → immutable datasets/vNNN/ в ml-datasets (put_or_fail
fail-loud) → manifest.json последним; журнал stage='export'. S3Store: bucket-параметр
конструктора с allowlist {raw,ml-datasets}, list_prefixes (CommonPrefixes+пагинация), get_object.

## Решения/отклонения
1. upload_or_fail (streaming с диска) для data-файлов вместо put_or_fail(bytes) — не читать
   весь parquet в память (bounded RAM NFR-001); манифест мал → put_or_fail байтами.
2. Decimal→строка в jsonl (точность), parquet decimal нативно — расхождение в манифесте notes.
3. pyarrow 25.0.0 (актуальная на реализации).

## Верификация (двойная)
- kulibin: export-demo v001 11 строк, parquet читается pandas независимо 11=COUNT(*), повтор→v++
  без перезаписи (fail-loud), манифест sha256==факт/target_populated=false, детерминизм
  content-sha, 0-HTTP тест, allowlist warehouse→ValueError, 133 passed.
- Tech Lead независимо: pytest 133 passed, ruff clean, smoke 4 passed; boto3-download последней
  версии → pandas.read_parquet 11 строк/23 колонки = row_count манифеста; target_populated=false,
  photo_handling=links, formats parquet+jsonl.

## Хвосты → stage-4/бэклог
PATCH устава I-4 (владельцу, не-блокер); фото только ссылки; ml-datasets накопил dev-версии
(immutable); jsonl decimal=строка vs parquet decimal (в манифесте).
