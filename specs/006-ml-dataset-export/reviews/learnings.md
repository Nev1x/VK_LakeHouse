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
