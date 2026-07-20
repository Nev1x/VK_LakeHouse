# Stage 1 — Creative Team, отчёт (006-ml-dataset-export)

Дата: 2026-07-20. Состав (делегированный): Creative Analyst + System Analyst.

## Решения
1. Формат: parquet (pyarrow — новая зависимость, оправдана DoD) + jsonl (stdlib + Decimal/
   timestamp encoder), both по умолчанию (jsonl из памяти дёшев).
2. Запись: Python читает features через Trino (FOR VERSION AS OF snapshot, ORDER BY id,
   chunked) → pyarrow parquet локально → S3Store в ml-datasets. Trino в ml-datasets НЕ пишет
   (UNLOAD/второй каталог — отклонено, избыточно).
3. Версионирование: list_objects max vNNN +1 (не реестр-таблица); fail-loud на коллизию (НЕ
   put_if_absent-skip как raw — два экспорта с одним vNNN ≠ тот же контент).
4. Immutable: guard object_exists + fail-loud; манифест последним (маркер валидности).
5. Фото: ТОЛЬКО ссылки (passthrough). Копии отклонены — SSRF (URL из непроверенных данных →
   внутренние data_net-адреса), storage, legal; отдельное решение владельца.
6. Детерминизм: пин snapshot + ORDER BY id → одинаковое содержимое; байт-в-байт parquet НЕ
   гарантируется (writer-метаданные) — критерий = хэш СОДЕРЖИМОГО, не сырого parquet.
7. Дата манифеста — datetime.now(UTC) python-стороны (не Trino current_timestamp).
8. Lock: общий pipeline-lock (System Analyst — сериализует со всем, проще; Creative предлагал
   отдельный export.lock — выбран общий как уже принятый паттерн).
9. is_loft всегда NULL — манифест честно target_populated:false (US-5).
10. КРИТИЧНО: I-4 decision record для прямой записи в ml-datasets (устав разрешает обход Trino
    только для raw/loader; ml-datasets — симметричная egress-зона выгрузки) — обязателен до
    stage-2, иначе аудит зарубит по I-4.

## CUT (YAGNI): train/test split, фото-копии, DVC/lakeFS, реестр-таблица версий,
партиционирование parquet, крипто-подпись манифеста.

## Риски (13) отражены в FR/Edge Cases
пустой features, is_loft NULL честность, гонка vNNN, TOCTOU snapshot, OOM chunked, SSRF (только
если копии), fail-loud коллизия, integrity-хэш, I-4 буква, Decimal/timestamp encoder,
частичный сбой (манифест последним), мусор в bucket.
