#!/bin/sh
# Генерация self-signed PKCS12 keystore для HTTPS Trino [FR-015, T6].
# Password-аутентификация Trino работает только по secure-каналу — HTTPS обязателен даже на loopback.
# Клиенты (smoke, loader 002) подключаются с verify=False (self-signed, доверенный периметр = машина).
# trino.p12 в git не попадает (.gitignore); регенерируется идемпотентно на каждый make up.
set -eu

: "${TRINO_KEYSTORE_PASSWORD:?TRINO_KEYSTORE_PASSWORD не задан — скопируй .env.example в .env}"

DIR="$(cd "$(dirname "$0")" && pwd)/auth"
mkdir -p "$DIR"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

openssl req -x509 -newkey rsa:2048 -nodes -days 3650 -subj "/CN=localhost" \
  -keyout "$TMP/key.pem" -out "$TMP/cert.pem" >/dev/null 2>&1
openssl pkcs12 -export -inkey "$TMP/key.pem" -in "$TMP/cert.pem" \
  -out "$DIR/trino.p12" -passout pass:"$TRINO_KEYSTORE_PASSWORD" -name trino >/dev/null 2>&1
chmod 600 "$DIR/trino.p12"
echo "gen-tls: $DIR/trino.p12 готов"
