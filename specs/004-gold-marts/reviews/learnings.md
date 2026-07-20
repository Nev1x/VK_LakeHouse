# Learnings — 004-gold-marts

## stage-1
- **Interpretations:** «feature-таблица для ML лофт/не-лофт» — при отсутствии меток в данных
  трактовано как экспорт ПРИЗНАКОВ с NULL-таргетом, не как эвристическая псевдо-разметка.
- **Deviations:** сжатый состав (2 субагента, делегированный режим).
- **Open questions:** нет (вопрос метки закрыт решением is_loft=NULL + разметка вне платформы).

## stage-2
- **Learnings:** строгий санитайзер идентификаторов ([a-z0-9_]) конфликтует с Iceberg
  metadata-именами ($snapshots) — нужен отдельный сборщик; approx_percentile в Trino не берёт
  DECIMAL (CAST AS DOUBLE); CTAS выводит DECIMAL(p,s) молча — фиксировать явным CAST, иначе
  случайный тип становится frozen-контрактом.
- **Deviations:** сжатый состав (делегированный режим).

## stage-3
- **Learnings:** CREATE OR REPLACE TABLE AS SELECT атомарен на Iceberg JDBC-каталоге и строго
  лучше rename-swap (нет not-found окна для читателя-дашборда); FOR VERSION AS OF пинит чтение
  на snapshot → детерминизм агрегатов; approx_percentile стабилен на фикс-snapshot.
- **Deviations:** CREATE OR REPLACE вместо rename-swap (spike-подтверждённое улучшение).
