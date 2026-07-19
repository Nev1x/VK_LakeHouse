# Intent-brief 001 — lakehouse-infra

**Цель.** Базовая инфраструктура LakeHouse «ЛофтНавигатор» на Docker Compose (локальная машина):
MinIO (объектное хранилище), PostgreSQL (JDBC-каталог Iceberg), Trino (SQL-движок с
Iceberg-коннектором), Grafana.

**Scope.**
- `docker-compose.yml` + `.env.example` (креды только через env — устав I-7).
- Три сети: `public_net` (Grafana, будущие entrypoints), `app_net`, `data_net`
  (Trino/MinIO/Postgres — наружу не публикуется, устав I-1).
- Healthchecks у всех сервисов; префикс контейнеров `loftnav`.
- Конфиг Trino-каталога `iceberg` (JDBC catalog → Postgres, warehouse → MinIO bucket).
- Bootstrap bucket'ов MinIO (`warehouse`, слои raw/bronze/silver/gold).
- Make-обёртки: `make up / down / smoke`.
- Smoke-тест: Trino отвечает, каталог `iceberg` виден, тестовая таблица создаётся и читается.
- `docs/architecture.md` — итоговая схема развёрнутого.

**Вне scope.** Ingestion, трансформации, дашборды (фичи 002–005).

**Зависимости.** Нет (первая фича).

**Готово, когда.** `make up` с нуля поднимает стек зелёным по healthchecks; smoke-тест проходит;
секретов в git нет.
