# ЛофтНавигатор (LoftNavigator)

Локальная data-платформа класса **LakeHouse** для объявлений о квартирах: принимает файлы
**любых форматов** (CSV / Excel / JSON — схемы заранее неизвестны), прогоняет их через
медальон-слои, строит витрины и дашборды и выпускает **версионированные датасеты** для будущего
обучения ML-модели «лофт / не лофт». Всё работает на одной машине, данные наружу не уходят.

```
файлы (CSV/XLSX/JSON)
      │  make ingest
      ▼
 raw (MinIO, ключ = sha256, immutable) ──► bronze (как есть, схема выведена)
      │  make transform  (TOML-маппинг, нормализация, карантин)
      ▼
 silver.apartments_clean (единая чистая модель, MERGE last-write-wins)
      │  make build-gold
      ▼
 gold: витрины (районы · стиль×ремонт×мебель · динамика) + apartments_features
      │  make export-dataset
      ▼
 ml-datasets/datasets/vNNN/  (parquet + jsonl + manifest.json, immutable)
```

## Стек

| Компонент | Роль |
|---|---|
| **MinIO** | объектное хранилище: сырьё, warehouse Iceberg, ML-датасеты |
| **Apache Iceberg** | табличный формат: ACID, снапшоты, эволюция схемы |
| **PostgreSQL** | JDBC-каталог Iceberg — только указатели, ни одной строки данных |
| **Trino** | SQL-движок поверх Iceberg; единственная дверь к таблицам |
| **Grafana** | дашборды как код («Операции платформы», «Квартиры») |
| **Python 3.12 + Make** | CLI-конвейер `loftnav`: ingest / transform / build-gold / export-dataset |

Всё поднимается одним `docker compose` (5 контейнеров), порты опубликованы **только на
127.0.0.1**: Grafana `:3000`, Trino HTTPS `:8080`, MinIO `:9000/:9001`, каталог Postgres
`:5432` (read-only роль для pgAdmin).

## Быстрый старт

```bash
cp .env.example .env        # заполнить креды (локальные, в git не попадают)
make up                     # поднять стек (докачает образы, дождётся healthy)
make smoke                  # смок-тесты живости
source .venv/bin/activate && set -a; . ./.env; set +a

make ingest FILE=data-in/apartments_full.csv   # любой CSV/XLSX/JSON
make transform                                  # bronze → silver по конфигам configs/mapping/
make build-gold                                 # витрины + фичи
make export-dataset                             # новая версия vNNN в MinIO
```

Дашборды: http://127.0.0.1:3000 · MinIO Console: http://127.0.0.1:9001.
Полный сценарий показа с пояснениями — **[docs/DEMO.md](docs/DEMO.md)**.

## Что платформа гарантирует

- **Идемпотентность приёма** — файл учитывается по sha256 содержимого: повторная загрузка
  того же сырья не задваивает данные.
- **Ни одна строка не теряется молча** — кривые значения уезжают в карантин
  (`iceberg.quarantine.*`) с человекочитаемой причиной; журнал `iceberg.ops.pipeline_runs`
  append-only и пишет честные счётчики даже при сбое.
- **Новый источник = один TOML-файл** в `configs/mapping/` (маппинг колонок, касты,
  enum-словари, конверсии единиц) — ни строчки кода.
- **Детерминированные витрины** — сборка от закреплённого снапшота Iceberg, точная медиана
  (не approx), повторный запуск даёт байт-в-байт тот же результат.
- **Экспорт immutable** — версии `vNNN` никогда не перезаписываются; `manifest.json`
  фиксирует снапшот, счётчики и sha256 — любой эксперимент воспроизводим.
- **Датасет читается без платформы** — обычный `pandas.read_parquet` по S3-ключу.

## ML-прицел

Витрина `gold.apartments_features` (и экспорт) — 26 признаков на объявление, включая
лофт-маркеры: `ceiling_height_m`, `wall_material`, `year_built`. Целевая колонка `is_loft`
намеренно пуста: размечать её эвристикой по стилю — утечка таргета; метки появятся отдельной
разметкой.

## Структура репозитория

```
src/loftnav/        CLI и конвейер (ingest / transform / gold / export)
configs/mapping/    TOML-маппинги источников → silver
infra/              compose-конфиги Trino/Postgres/MinIO/Grafana (дашборды — as code)
tests/              pytest: юниты + интеграционные на живом стеке (144)
docs/               architecture.md · constitution.md (16 инвариантов) · DEMO.md
specs/              спецификации фич 001–007 (spec → plan → state → audit)
data-in/            примеры входных файлов (6050 реальных объявлений)
```

## Безопасность (по уставу проекта)

Секреты только в `.env` (в git — никогда); Trino отдаёт пароль только по HTTPS;
Postgres-каталог доступен снаружи только read-only ролью; все порты — loopback;
доступ к данным — исключительно через Trino.
