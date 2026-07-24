# Шпаргалка команд ЛофтНавигатора — что делает каждая и как читать вывод

Словарь: **run_id** — квитанция запуска (по ней прогон ищется в журнале).
Статусы: `[success]` — всё прошло · `[partial]` — прошло, часть строк в карантине ·
`[skipped]` — уже сделано раньше, повтора нет · `[failed]` — не прошло.
Слои: **bronze** «как привезли» → **silver** «почищено» → **gold** «посчитано для людей».

---

## 0. Подготовка терминала (каждый новый терминал!)

```bash
cd ~/Desktop/VK
source .venv/bin/activate      # включить python-окружение проекта (в строке появится (.venv))
set -a; . ./.env; set +a       # загрузить пароли/адреса из .env; вывода нет — это норма
```
Без второй строки любая команда упадёт с текстом «Переменная окружения … не задана».

## 1. Стек: включить / проверить / выключить

```bash
make up      # поднять 5 контейнеров и дождаться их готовности
make ps      # показать статус
make down    # выключить (данные сохраняются)
make logs    # хвост логов всех контейнеров, если что-то странное
```
**Сработало:** в `make ps` у каждого контейнера `Up … (healthy)` — Docker сам опросил
сервисы «ты жив?» и получил «да».

## 2. Смок-тесты

```bash
make smoke           # платформа дышит: Trino отвечает, MinIO отвечает, каталог на месте
make grafana-smoke   # Grafana жива: датасорс подключён, дашборды загружены
```
**Сработало:** `4 passed` (число упавших не показано = ноль).

## 3. Изготовить демо-файл (нарочно кривой CSV)

```bash
RUN=$(date +%s)
printf 'id;price;area;rooms;district;renov\nD1-%s;6500;52,0;2;Пресненский;евро\nD2-%s;8100;71,5;3;Якиманка;черновая\nD3-%s;0;40,0;1;Басманный;евро\n' "$RUN" "$RUN" "$RUN" > /tmp/demo.csv
cat /tmp/demo.csv    # показать файл аудитории
```
- `date +%s` — текущее время числом; `RUN=$(...)` — сохранить его в переменную.
  Зачем: платформа узнаёт файлы по отпечатку содержимого — одинаковый файл она повторно
  не примет. Время в id делает файл уникальным на каждый показ.
- `printf` — печать по шаблону: `\n` — перевод строки, `%s` — дырка, куда подставляется
  `"$RUN"` (три дырки — три подстановки); `> /tmp/demo.csv` — сохранить в файл, а не на экран.
- Файл нарочно неудобный: разделитель `;`, десятичная запятая («52,0»), цена в тысячах
  («6500» = 6,5 млн), ремонт словами, третья строка с ценой 0 — битая, для карантина.

## 4. Приём файла (ingest)

```bash
python -m loftnav.cli ingest --source t_avito /tmp/demo.csv
```
Кладёт сырой файл в архив и раскладывает строки в bronze-таблицу источника `t_avito`.
Качество НЕ проверяет — сырьё не судим.
```
step=raw key=raw/<sha256>/demo.csv stored=True   ← сырьё в архиве, ключ = отпечаток файла
step=bronze source=t_avito rows_ok=3             ← 3 строки разложены в bronze
[success ] demo.csv  ok=3 quarantined=0          ← итог: принято 3
```

## 5. Повторный приём того же файла (идемпотентность)

```bash
python -m loftnav.cli ingest --source t_avito /tmp/demo.csv   # та же команда ещё раз
```
```
step=skip reason=hash-match-success              ← файл узнан по отпечатку
[skipped ] demo.csv  ok=0 quarantined=0          ← данные НЕ задвоились
```
**Фраза:** «Тот же файл дважды — дубликатов нет. Это фича, а не отказ».

## 6. Очистка bronze → silver (transform)

```bash
python -m loftnav.cli transform --source t_avito
```
Переименовывает колонки по TOML-конфигу (`configs/mapping/`), приводит типы
(«6500 тыс» → 6 500 000 ₽; «52,0» → 52.00), проверяет здравый смысл (цена > 0, площадь
1–1000 м²…). Что не прошло — в карантин с причиной.
```
step=partition source=t_avito rows_ok=2 rejects=1   ← 2 чистые, 1 отбракована
[partial ] t_avito  ok=2 quarantined=1 partitions=1 ← частичный успех; это честность, не ошибка
```

## 7. Почему строку отбраковали (карантин)

```bash
python -c "from loftnav.trino_client import get_connection; c=get_connection().cursor(); \
c.execute(\"SELECT reason FROM iceberg.quarantine.silver_t_avito_rejects ORDER BY rejected_at DESC LIMIT 1\"); print(c.fetchone()[0])"
```
SQL-вопрос платформе: «причина последней отбраковки?»
**Вывод:** `поле price_rub=Decimal('0.00') вне sanity-диапазона` — цена ноль, так не бывает.
**Фраза:** «Строка не потеряна и не уронила загрузку — лежит в карантине с причиной».

## 8. Пересчёт витрин (build-gold)

```bash
python -m loftnav.cli build-gold
```
Из silver считает 4 готовые таблицы: цены по районам · срезы стиль×ремонт×мебель ·
динамика загрузок · признаки для ML.
```
[success ] mart_price_area_by_district  rows_ok=14   ← районов (12 реальных + 2 демо)
[success ] mart_style_renovation_furniture rows_ok=78
[success ] mart_listing_dynamics  rows_ok=2
[success ] apartments_features  rows_ok=6056         ← квартир × 26 признаков
```
`rows_ok` — сколько строк получилось в каждой витрине.

## 9. Что внутри PostgreSQL (pgAdmin, до этого §2 — держать вкладку открытой)

Подключение: host `127.0.0.1`, port `5432`, база `iceberg_catalog`, пользователь
`loftnav_ro` (пароль `LOFTNAV_RO_PASSWORD` в .env). Query Tool:
```sql
SELECT table_namespace, table_name, substring(metadata_location,1,60) AS metadata
FROM iceberg_tables ORDER BY 1,2;
```
**Ключевой слайд:** в PostgreSQL НЕТ ни одной квартиры — только каталог-указатели на
файлы в MinIO. После transform/build-gold перезапусти запрос (F5): `metadata_location`
сменился — каждая запись данных атомарно переставляет указатель.
Фолбэк без pgAdmin:
```bash
docker compose exec postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -c "SELECT table_namespace, table_name, substring(metadata_location,1,60) FROM iceberg_tables ORDER BY 1,2"
```

## 10. Глазами: Grafana и MinIO (браузер, не команды)

- Grafana http://127.0.0.1:3000 (креды `GRAFANA_ADMIN_*` из .env): «Операции платформы» —
  статусы прогонов, наша отбракованная строка, реестр карантина; «Квартиры» — цены по
  районам, срезы, динамика.
- MinIO http://127.0.0.1:9001 (креды `MINIO_ROOT_*`): бакеты raw (сырьё по sha256),
  warehouse (parquet Iceberg), ml-datasets → открыть `manifest.json` свежей версии.

## 11. Экспорт датасета для ML

```bash
python -m loftnav.cli export-dataset
```
Собирает из gold-признаков датасет и кладёт в хранилище новой нестираемой версией.
```
step=start version=v118 snapshot=8311…   ← новая версия; snapshot = замороженный момент данных
step=done  rows_ok=6056 files=['data.parquet','data.jsonl','manifest.json']
[success ] v118  rows_ok=6056
```
Старые версии не тронуты — эксперименты воспроизводимы; `manifest.json` — паспорт версии.

## 12. Финал: датасет читается обычным pandas (платформа не нужна)

Копировать в терминал ЦЕЛИКОМ, вместе с `python << 'EOF'` и закрывающим `EOF`:
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
**Вывод:** таблица 8 строк с районами, ценами, потолками, стенами, годом.
`is_loft = None` — намеренно: разметка эвристикой = утечка таргета.

## 13. После показа — вернуть эталон

```bash
python -c "from loftnav.trino_client import get_connection; c=get_connection().cursor(); \
c.execute(\"DELETE FROM iceberg.silver.apartments_clean WHERE source='t_avito'\"); c.fetchall(); \
c.execute('DROP TABLE IF EXISTS iceberg.quarantine.silver_t_avito_rejects'); c.fetchall()"
python -m loftnav.cli build-gold
```
Удаляет демо-строки из silver, чистит их карантин, пересчитывает витрины.
**Сработало:** в build-gold снова `rows_ok=12` районов и `rows_ok=6050` квартир.

---

Рефрен: у каждой команды в последней строке — **статус** («получилось ли») и **счётчики**
(«сколько именно»), а run_id — «где это записано в журнале». Ничего не происходит молча.
