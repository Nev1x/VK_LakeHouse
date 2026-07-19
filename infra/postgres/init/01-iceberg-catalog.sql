-- Пред-создание служебных таблиц JDBC-каталога Iceberg (V0-схема) [FR-004].
-- Iceberg 1.11 с дефолтом init-catalog-tables=false НЕ создаёт их сам, а Trino не публикует флаг
-- инициализации (валидное свойство отсутствует — проверено эмпирически, I-13). Trino/Iceberg на
-- первом обращении к каталогу выполнит updateSchemaIfRequired: ALTER TABLE ADD COLUMN iceberg_type
-- (V0 -> V1) идемпотентно. DDL — точные константы из org.apache.iceberg.jdbc.JdbcUtil (1.11.0).
-- Скрипт исполняется postgres-энтрипойнтом один раз на свежем volume (как POSTGRES_USER/POSTGRES_DB).

CREATE TABLE IF NOT EXISTS iceberg_tables (
    catalog_name               VARCHAR(255)  NOT NULL,
    table_namespace            VARCHAR(255)  NOT NULL,
    table_name                 VARCHAR(255)  NOT NULL,
    metadata_location          VARCHAR(1000),
    previous_metadata_location VARCHAR(1000),
    PRIMARY KEY (catalog_name, table_namespace, table_name)
);

CREATE TABLE IF NOT EXISTS iceberg_namespace_properties (
    catalog_name   VARCHAR(255)  NOT NULL,
    namespace      VARCHAR(255)  NOT NULL,
    property_key   VARCHAR(255),
    property_value VARCHAR(1000),
    PRIMARY KEY (catalog_name, namespace, property_key)
);
