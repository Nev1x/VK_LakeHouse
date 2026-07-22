# Демо ЛофтНавигатора — сценарий показа (~15 минут)

Предусловие: `make ps` — 4 контейнера healthy; venv активирован; `set -a; . ./.env; set +a`.

## 0. О чём проект (1 мин)
ЛофтНавигатор — локальная дата-платформа LakeHouse для объявлений о квартирах: приём файлов
любых форматов (CSV/Excel/JSON, схемы заранее неизвестны) → единая чистая модель → витрины и
дашборды → версионированные датасеты для обучения ML («лофт / не лофт»). Всё на одной машине,
данные наружу не уходят. Слои: raw → bronze → silver → gold (медальон).
Стек: MinIO + PostgreSQL (JDBC-каталог Iceberg) + Trino + Grafana, Docker Compose.

## 1. Живые данные (2 мин)
Загружено 6050 реальных объявлений из трёх форматов: CSV 3000 + Excel 3000 + JSON 50
(урезанная схема). Один загрузчик, схема выведена автоматически, Excel-лист стал источником сам.

## 2. Приём «кривого» файла вживую (3 мин)
```bash
printf 'id;price;area;rooms;district;renov\nD1;6500;52,0;2;Пресненский;евро\nD2;8100;71,5;3;Якиманка;черновая\nD3;0;40,0;1;Басманный;евро\n' > /tmp/demo.csv
python -m loftnav.cli ingest --source t_avito /tmp/demo.csv      # ok=3 — сырьё не судим
python -m loftnav.cli transform --source t_avito                  # partial ok=2 quarantined=1
```
Карантин с причиной (не потеряли и не упали):
```bash
python -c "from loftnav.trino_client import get_connection; c=get_connection().cursor(); \
c.execute(\"SELECT reason FROM iceberg.quarantine.silver_t_avito_rejects ORDER BY rejected_at DESC LIMIT 1\"); print(c.fetchone()[0])"
```
Нормализация: 6500 тыс → 6 500 000 ₽; «52,0» → 52.00 м²; «евро» → has_renovation=true.
Показать configs/mapping/t_avito.toml: новый источник = один TOML, ни строчки кода.
```bash
python -m loftnav.cli build-gold                                  # ~9 сек
```

## 3. Grafana — http://127.0.0.1:3000 (4 мин; креды в .env)
«Операции платформы»: статус прогонов по стадиям · принято/отбраковано (видна наша 1 строка) ·
свежесть слоёв · таблица failed с текстом ошибок · реестр quarantine.
«Квартиры»: цены/площади по 12 районам · срезы стиль×ремонт×мебель (пометка малых выборок) ·
динамика загрузок. Медиана детерминированная (точная — багфикс, вскрытый реальными данными).

## 4. «pgAdmin»: что внутри PostgreSQL (2 мин)
pgAdmin не ставили, Postgres наружу не выставлен (безопасность). Показ каталога одной командой:
```bash
docker compose exec postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -c "SELECT table_namespace, table_name, substring(metadata_location,1,60) AS metadata FROM iceberg_tables ORDER BY 1,2"
```
Ключевой слайд: в PostgreSQL НЕТ ни одной квартиры — только каталог-указатели на metadata в
MinIO. Данные = parquet в MinIO, версии/ACID = Iceberg, SQL = Trino. Это и есть LakeHouse.

## 5. MinIO — http://127.0.0.1:9001 (1.5 мин; креды MINIO_ROOT_* из .env)
Bucket raw (сырьё, ключ=sha256 — immutable) · warehouse (parquet+metadata Iceberg) ·
ml-datasets → datasets/vNNN/ → открыть manifest.json (версия, снапшот, 6050 строк, sha256,
target_populated:false — честно: метки нет, только признаки).

## 6. Финал — датасет для нейронки (2 мин)
```bash
python -m loftnav.cli export-dataset                              # новая версия vNNN
```
```python
import pandas as pd, boto3, io, os
s3 = boto3.client("s3", endpoint_url=os.environ["MINIO_ENDPOINT_URL"],
    aws_access_key_id=os.environ["MINIO_ROOT_USER"], aws_secret_access_key=os.environ["MINIO_ROOT_PASSWORD"])
r = s3.list_objects_v2(Bucket="ml-datasets", Prefix="datasets/", Delimiter="/")
last = sorted(p["Prefix"] for p in r["CommonPrefixes"])[-1]
df = pd.read_parquet(io.BytesIO(s3.get_object(Bucket="ml-datasets", Key=last+"data.parquet")["Body"].read()))
print(df[["district","price_rub","area_m2","ceiling_height_m","wall_material","year_built","is_loft"]].head(8))
```
Обычный pandas, платформа не нужна. Лофт-маркеры (потолки/стены/год) — признаки для модели;
is_loft — заготовка под разметку; версии immutable — эксперименты воспроизводимы.
Закрытие: «от кривого CSV до ML-датасета — четыре команды; наблюдаемо, без потерь, версионировано».

## Если что-то пошло не так
- make up падает на pull → корп-VPN; стек уже поднят, up не нужен (или `docker compose up -d --wait`).
- Панель Grafana в ошибке → Trino прогревается, обновить через 30 сек.
- Терминал «завис» на make → тихая проверка зависимостей ~5 сек, подождать.
