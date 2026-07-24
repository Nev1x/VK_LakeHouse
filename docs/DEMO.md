# Демо ЛофтНавигатора — 5 минут, на реальных данных

Предусловие: `make ps` — 4 контейнера healthy; в терминале показа:
```bash
cd ~/Desktop/VK && source .venv/bin/activate && set -a; . ./.env; set +a
```
Предполёт после репетиций: если показывали бонус-трек с кривым CSV — выполнить «Вернуть
эталон» (внизу); `python -m loftnav.cli transform --source t_avito` должен ответить
`partitions=0`. Базовая пятиминутка эталон не портит — её можно гонять подряд.

## 0. Одной фразой (30 сек)
«ЛофтНавигатор — локальная LakeHouse-платформа: принимает файлы с квартирами в любых
форматах, послойно чистит их (raw → bronze → silver → gold), показывает дашборды и выпускает
версионированные датасеты для обучения ML "лофт / не лофт". Всё на одной машине, ни одна
строка не теряется молча. Стек: MinIO + Iceberg + PostgreSQL-каталог + Trino + Grafana».

## 1. Реальные данные вживую (~2.5 мин)
```bash
ls -lh data-in/                                # исходники: CSV 3000 + JSON 3000 + XLSX 3000 + сэмпл 50
make ingest FILE=data-in/apartments_full.csv   # [skipped] hash-match — файл узнан по sha256:
                                               # сырьё не задваивается, даже если прислали повторно
python -m loftnav.cli transform --reprocess apartments   # ~50 сек — запустить и рассказывать
```
Пока крутится reprocess: «Сейчас 6000 строк из CSV и JSON заново проходят полную очистку:
переименование колонок по конфигу, типы, диапазоны здравого смысла, дедупликация. Новый
источник данных = один TOML-файл, ни строчки кода».
Итог на экране: **`[success] ok=6000 quarantined=0 partitions=2`**. Контроль:
```bash
python -c "from loftnav.trino_client import get_connection; c=get_connection().cursor(); \
c.execute(\"SELECT source, count(*) FROM iceberg.silver.apartments_clean GROUP BY 1 ORDER BY 2 DESC\"); \
[print(r) for r in c.fetchall()]"
```
→ 3000 + 3000 + 50 = **6050**. «В bronze было 6000 строк из двух файлов, в silver — 3000:
CSV и JSON содержат одни и те же квартиры, слияние по id дедуплицировало».
Замыкаем медальон — gold-стадия (~9 сек):
```bash
python -m loftnav.cli build-gold
```
→ четыре `[success]`: витрина районов (12), срезы стиль×ремонт×мебель (76), динамика,
признаки для ML (6050×26). «Из чистого silver пересчитаны готовые витрины — дашборд не
считает 6050 строк на лету, он читает готовый ответ. Пошли смотреть глазами».

## 2. Grafana — глазами (1 мин) — http://127.0.0.1:3000 (креды в .env)
Дашборд «Квартиры»: цены и площади по 12 районам, срезы стиль×ремонт×мебель (пометка малых
выборок), всё на живых 6050. «Медиана точная и детерминированная — приближённую функцию
реальные данные поймали на недетерминизме, починили с тестом-гвардом».

## 3. Финал — датасет для нейронки (1.5 мин)
```bash
python -m loftnav.cli export-dataset           # ~10 сек: новая immutable-версия vNNN
```
Копировать целиком, вместе с `python << 'EOF'` и `EOF`:
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
«Обычный pandas — платформа потребителю не нужна. Лофт-маркеры (потолки/стены/год) — признаки
для модели; is_loft пуст намеренно: эвристика = утечка таргета. Версии immutable —
эксперименты воспроизводимы».
Закрытие: «Любой файл → проверенная таблица → витрина → ML-датасет. Наблюдаемо, без потерь,
версионировано — три команды».

## Бонус-треки (если появилось время / пошли вопросы)

**Кривой CSV → карантин (2 мин):**
```bash
RUN=$(date +%s)   # уникализация: без неё повтор показа = skip по sha256
printf 'id;price;area;rooms;district;renov\nD1-%s;6500;52,0;2;Пресненский;евро\nD2-%s;8100;71,5;3;Якиманка;черновая\nD3-%s;0;40,0;1;Басманный;евро\n' "$RUN" "$RUN" "$RUN" > /tmp/demo.csv
python -m loftnav.cli ingest --source t_avito /tmp/demo.csv      # ok=3 — сырьё не судим
python -m loftnav.cli transform --source t_avito                  # partial ok=2 quarantined=1
python -c "from loftnav.trino_client import get_connection; c=get_connection().cursor(); \
c.execute(\"SELECT reason FROM iceberg.quarantine.silver_t_avito_rejects ORDER BY rejected_at DESC LIMIT 1\"); print(c.fetchone()[0])"
```
«Цена 0 — в карантине с причиной; 6500 тыс → 6 500 000 ₽; строка не потеряна, конвейер не упал».

**pgAdmin — что внутри PostgreSQL (1.5 мин):** host 127.0.0.1:5432, база `iceberg_catalog`,
пользователь `loftnav_ro` (пароль `LOFTNAV_RO_PASSWORD` в .env, read-only):
```sql
SELECT table_namespace, table_name, substring(metadata_location,1,60) AS metadata
FROM iceberg_tables ORDER BY 1,2;
```
«В PostgreSQL НЕТ ни одной квартиры — только каталог-указатели на metadata в MinIO. Данные =
parquet в MinIO, ACID = Iceberg, SQL = Trino — это и есть LakeHouse». После transform — F5:
указатель сменился.

**MinIO Console (1 мин):** http://127.0.0.1:9001 (креды MINIO_ROOT_*): бакеты raw (сырьё,
ключ=sha256) · warehouse (parquet Iceberg) · ml-datasets → datasets/vNNN/ → manifest.json.

## Вернуть эталон (после бонус-трека с кривым CSV; не при зрителях)
```bash
python -c "from loftnav.trino_client import get_connection; c=get_connection().cursor(); \
c.execute(\"DELETE FROM iceberg.silver.apartments_clean WHERE source='t_avito'\"); c.fetchall(); \
c.execute('DROP TABLE IF EXISTS iceberg.quarantine.silver_t_avito_rejects'); c.fetchall()"
python -m loftnav.cli build-gold
```
Ожидаем: `mart_price_area_by_district rows_ok=12`, `apartments_features rows_ok=6050`.

## Если что-то пошло не так
- make up падает на pull → корп-VPN; стек уже поднят, up не нужен (или `docker compose up -d --wait`).
- Панель Grafana в ошибке → Trino прогревается, обновить через 30 сек.
- Терминал «завис» на make → тихая проверка зависимостей ~5 сек, подождать.
- pgAdmin не подключается → тот же запрос из терминала:
  `docker compose exec postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT table_namespace, table_name, substring(metadata_location,1,60) FROM iceberg_tables ORDER BY 1,2"`.
