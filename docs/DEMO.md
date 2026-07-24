# Демо ЛофтНавигатора — сценарий показа (~15 минут)

Предусловие: `make ps` — 4 контейнера healthy; venv активирован; `set -a; . ./.env; set +a`.
Предполётная проверка (после репетиций обязательна): выполнить §7 «вернуть эталон», затем
`python -m loftnav.cli transform --source t_avito` должен ответить `partitions=0` — очередь
источника пуста. Иначе transform в §2 пакетно подберёт хвосты репетиций, и счётчики будут
больше сценарных (это не ошибка — очистка выгребает всё непереработанное, — но удивляет).

## 0. О чём проект (1 мин)
ЛофтНавигатор — локальная дата-платформа LakeHouse для объявлений о квартирах: приём файлов
любых форматов (CSV/Excel/JSON, схемы заранее неизвестны) → единая чистая модель → витрины и
дашборды → версионированные датасеты для обучения ML («лофт / не лофт»). Всё на одной машине,
данные наружу не уходят. Слои: raw → bronze → silver → gold (медальон).
Стек: MinIO + PostgreSQL (JDBC-каталог Iceberg) + Trino + Grafana, Docker Compose.

## 1. Живые данные — работа с реальными файлами (3.5 мин)
Исходники лежат в data-in/: CSV 3000 строк + JSON 3000 (те же квартиры) + Excel 3000 +
урезанный JSON 50. Один загрузчик, схема выведена автоматически, Excel-лист стал источником сам.
```bash
ls -lh data-in/                                # вот они: три файла-трёхтысячника + сэмпл
make ingest FILE=data-in/apartments_full.csv   # [skipped] hash-match-success — 3000 строк уже
                                               # приняты, файл узнан по sha256 (идемпотентность)
python -m loftnav.cli transform --reprocess apartments   # переиграть очистку ВЖИВУЮ: ~50 сек
```
Пока крутится reprocess, рассказать: сейчас 6000 строк (CSV + JSON) заново проходят все
правила очистки — типы, диапазоны, дедупликация. Итог: `[success] ok=6000 quarantined=0
partitions=2`. В silver при этом 3000: CSV и JSON содержат одни и те же квартиры, слияние
по id дедуплицирует — «последняя версия объявления побеждает». Проверка расклада:
```bash
python -c "from loftnav.trino_client import get_connection; c=get_connection().cursor(); \
c.execute(\"SELECT source, count(*) FROM iceberg.silver.apartments_clean GROUP BY 1 ORDER BY 2 DESC\"); \
[print(r) for r in c.fetchall()]"
```
→ apartments 3000 · apartments_apartments 3000 · apartments_lite 50 = **6050 реальных квартир**.

## 2. Приём «кривого» файла вживую (3 мин)
```bash
RUN=$(date +%s)   # уникализируем содержимое per-run: ingest идемпотентен по sha256, без этого повтор показа = skip
printf 'id;price;area;rooms;district;renov\nD1-%s;6500;52,0;2;Пресненский;евро\nD2-%s;8100;71,5;3;Якиманка;черновая\nD3-%s;0;40,0;1;Басманный;евро\n' "$RUN" "$RUN" "$RUN" > /tmp/demo.csv
python -m loftnav.cli ingest --source t_avito /tmp/demo.csv      # ok=3 — сырьё не судим
python -m loftnav.cli ingest --source t_avito /tmp/demo.csv      # [skipped] ok=0 — идемпотентность: то же сырьё не задваивается (это фича)
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
«Квартиры»: цены/площади по районам (12 реальных + 2 демо после нашей вставки) · срезы стиль×ремонт×мебель (пометка малых выборок) ·
динамика загрузок. Медиана детерминированная (точная — багфикс, вскрытый реальными данными).

## 4. pgAdmin: что внутри PostgreSQL (2 мин)
Подключение (настроить до показа): host 127.0.0.1, port 5432, база `iceberg_catalog`,
пользователь `loftnav_ro` — read-only роль (пароль `LOFTNAV_RO_PASSWORD` в .env; порт
опубликован только на 127.0.0.1, писать в каталог роль не может). Query Tool:
```sql
SELECT table_namespace, table_name, substring(metadata_location,1,60) AS metadata
FROM iceberg_tables ORDER BY 1,2;
```
Ключевой слайд: в PostgreSQL НЕТ ни одной квартиры — только каталог-указатели на metadata в
MinIO. Данные = parquet в MinIO, версии/ACID = Iceberg, SQL = Trino. Это и есть LakeHouse.
Трюк-свидетель: вкладку pgAdmin открой ещё ДО §2 и покажи каталог «до». После
transform/build-gold перезапусти запрос (F5): `metadata_location` у silver/gold сменился
на глазах. Каждый коммит Iceberg атомарно переставляет указатель — это вся роль Postgres.

## 5. MinIO — http://127.0.0.1:9001 (1.5 мин; креды MINIO_ROOT_* из .env)
Bucket raw (сырьё, ключ=sha256 — immutable) · warehouse (parquet+metadata Iceberg) ·
ml-datasets → datasets/vNNN/ → открыть manifest.json (версия, снапшот, 6050 строк, sha256,
target_populated:false — честно: метки нет, только признаки).

## 6. Финал — датасет для нейронки (2 мин)
```bash
python -m loftnav.cli export-dataset                              # новая версия vNNN
```
Копируется в терминал целиком (python-heredoc, НЕ построчно в zsh):
```bash
python << 'EOF'
import pandas as pd, boto3, io, os
s3 = boto3.client("s3", endpoint_url=os.environ["MINIO_ENDPOINT_URL"],
    aws_access_key_id=os.environ["MINIO_ROOT_USER"], aws_secret_access_key=os.environ["MINIO_ROOT_PASSWORD"])
r = s3.list_objects_v2(Bucket="ml-datasets", Prefix="datasets/", Delimiter="/")
last = sorted(p["Prefix"] for p in r["CommonPrefixes"])[-1]
df = pd.read_parquet(io.BytesIO(s3.get_object(Bucket="ml-datasets", Key=last+"data.parquet")["Body"].read()))
print(df[["district","price_rub","area_m2","ceiling_height_m","wall_material","year_built","is_loft"]].head(8))
EOF
```
Обычный pandas, платформа не нужна. Лофт-маркеры (потолки/стены/год) — признаки для модели;
is_loft — заготовка под разметку; версии immutable — эксперименты воспроизводимы.
Закрытие: «от кривого CSV до ML-датасета — четыре команды; наблюдаемо, без потерь, версионировано».

## 7. После демо — вернуть эталон (1 мин)
Демо-строки одноразовые: убираем их из silver и чистим карантин источника, платформа возвращается
в эталон (silver 6050, 12 районов). Сырьё `bronze.t_avito` НЕ трогаем — raw immutable.
```bash
python -c "from loftnav.trino_client import get_connection; c=get_connection().cursor(); \
c.execute(\"DELETE FROM iceberg.silver.apartments_clean WHERE source='t_avito'\"); c.fetchall(); \
c.execute('DROP TABLE IF EXISTS iceberg.quarantine.silver_t_avito_rejects'); c.fetchall()"
python -m loftnav.cli build-gold                                  # витрины пересчитаны из silver
python -c "from loftnav.trino_client import get_connection; c=get_connection().cursor(); \
c.execute('SELECT count(*) FROM iceberg.silver.apartments_clean'); print('silver:', c.fetchone()[0]); \
c.execute('SELECT count(*) FROM iceberg.gold.mart_price_area_by_district'); print('районов:', c.fetchone()[0])"
```
Ожидаем `silver: 6050` и `районов: 12` — эталон восстановлен.

## Если что-то пошло не так
- make up падает на pull → корп-VPN; стек уже поднят, up не нужен (или `docker compose up -d --wait`).
- Панель Grafana в ошибке → Trino прогревается, обновить через 30 сек.
- Терминал «завис» на make → тихая проверка зависимостей ~5 сек, подождать.
- pgAdmin не подключается → тот же запрос из терминала:
  `docker compose exec postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT table_namespace, table_name, substring(metadata_location,1,60) FROM iceberg_tables ORDER BY 1,2"`.
