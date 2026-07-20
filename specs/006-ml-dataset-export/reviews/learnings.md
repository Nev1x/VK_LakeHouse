# Learnings — 006-ml-dataset-export

## stage-1
- **Interpretations:** «ссылки/копии фото» intent → только ссылки (копии = SSRF/legal-риск,
  отдельное решение); «одинаковый вход→одинаковый датасет» → идентичность содержимого, не байт
  parquet (writer-метаданные).
- **Deviations:** сжатый состав (делегированный режим).
- **Open questions:** пустой-features success-vs-fail — решить в spec (FR-010 фиксирует явно).

## stage-2
- **Learnings:** I-4 регулирует ЧТЕНИЕ managed-таблиц в обход Trino, не запись egress-артефактов
  вне каталога — ml-datasets симметричен raw (оба owned-фичей, вне Iceberg); текст устава
  («единственное исключение») отстал от архитектуры 001 → рекомендован PATCH (решение владельца,
  не агента). pandas.to_parquet пишет целиком — для bounded-памяти нужен ParquetWriter по чанкам.
- **Deviations:** FR-004 переформулирован по варианту (б) обоих ревьюеров (egress вне периметра
  I-4, не «второе исключение») — снимает текстовое напряжение без ослабления инварианта.

## stage-3
- **Learnings:** pyarrow.parquet.ParquetWriter — потоковая запись по чанкам (bounded RAM),
  df.to_parquet пишет целиком; MinIO list_objects_v2 Delimiter → CommonPrefixes + пагинация
  обязательна (иначе занижение max→коллизия версий); загрузка больших файлов — streaming с
  диска (upload_file), не чтение в память для put.
- **Deviations:** upload_or_fail streaming вместо put_or_fail(bytes) для data-файлов.

## stage-3 (fix после stage-4)
- **Learnings:** общий lock-модуль ingest/run.py используется всеми стадиями — сообщение об
  ошибке должно быть нейтральным ('конвейер уже занят'), не привязанным к ingest.

## stage-4
- **Learnings:** финальная фича замкнула пайплайн; адверсарный QA подтвердил independent
  parquet-read (главный DoD-критерий 006) 3-осевой сверкой row_count; immutability fail-loud
  и allowlist S3Store — ключевые защиты egress-зоны.
- **Deviations:** проход 1 WARNING (lock-текст) → fix (retry 1).
