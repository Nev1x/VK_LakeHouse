#!/bin/sh
# minio-init: идемпотентный bootstrap bucket'ов LakeHouse [T7, FR-005]
# raw (immutable исходники), warehouse (managed Iceberg bronze/silver/gold), ml-datasets (под 006).
set -eu

# minio-init стартует после service_healthy minio, но alias может застать раннюю инициализацию —
# короткий retry с таймаутом (не зависание, I-8/I-9).
i=0
until mc alias set local "http://minio:9000" "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null 2>&1; do
  i=$((i + 1))
  if [ "$i" -ge 15 ]; then
    echo "minio-init: MinIO недоступен по http://minio:9000 после 15 попыток" >&2
    exit 1
  fi
  sleep 2
done

for b in raw warehouse ml-datasets; do
  mc mb --ignore-existing "local/$b"
done

echo "minio-init: buckets ready (raw, warehouse, ml-datasets)"
