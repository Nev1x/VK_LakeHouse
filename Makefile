# LoftNavigator LakeHouse — управление стеком (фича 001).
# macOS/BSD-совместимо: логика в POSIX-sh рецептах, без GNU-специфики make.
.POSIX:
.PHONY: help up down smoke ps logs deps gen-auth bootstrap ingest ingest-demo \
        transform transform-demo build-gold build-gold-demo grafana-smoke \
        export-dataset export-dataset-demo check-env check-docker

COMPOSE = docker compose
VENV    = .venv
PY      = $(VENV)/bin/python
INGEST_DEMO_DIR = tests/fixtures/ingestion
TRANSFORM_DEMO_DIR = tests/fixtures/transform

help:
	@echo "LoftNavigator LakeHouse — make-цели:"
	@echo "  make up            — поднять стек с нуля (pull -> up -> ожидание healthy)"
	@echo "  make down          — остановить стек (именованные volumes СОХРАНЯЮТСЯ; НЕ -v)"
	@echo "  make smoke         — round-trip smoke: Trino -> Iceberg -> MinIO"
	@echo "  make ingest FILE=  — загрузить файл/папку в bronze (фича 002)"
	@echo "  make ingest-demo   — загрузить демо-фикстуры tests/fixtures/ingestion/"
	@echo "  make transform ARGS=... — bronze -> silver.apartments_clean (фича 003)"
	@echo "  make transform-demo — ingest демо-источников + transform в silver"
	@echo "  make build-gold ARGS=... — silver -> gold-витрины + features (фича 004)"
	@echo "  make build-gold-demo — transform-demo + build-gold (цепочка ingest->gold)"
	@echo "  make ps / logs     — диагностика"

check-docker:
	@docker info >/dev/null 2>&1 || { echo "ERROR: Docker daemon не запущен — запусти Docker Desktop и повтори."; exit 1; }

check-env:
	@test -f .env || { echo "ERROR: нет файла .env. Выполни: cp .env.example .env  и заполни значения (openssl rand -hex 24)."; exit 1; }

deps:
	@if [ ! -x "$(PY)" ]; then \
	  if command -v uv >/dev/null 2>&1; then uv venv --python 3.12 $(VENV); \
	  else python3 -m venv $(VENV); fi; \
	fi
	@if command -v uv >/dev/null 2>&1; then uv pip install --python $(VENV) -q -e ".[dev]"; \
	 else $(PY) -m pip install -q -e ".[dev]"; fi

gen-auth: check-env deps
	@set -a; . ./.env; set +a; $(PY) infra/trino/gen_password.py; sh infra/trino/gen-tls.sh

up: check-docker check-env gen-auth
	@echo ">>> pull образов (может занять время на первом запуске)..."
	@$(COMPOSE) pull
	@echo ">>> запуск стека и ожидание healthy..."
	@$(COMPOSE) up -d --wait --wait-timeout 240
	@$(MAKE) bootstrap
	@$(COMPOSE) ps

# bootstrap namespace'ов medallion (bronze/silver/gold/quarantine) — контракт для 002-006
bootstrap: check-env deps
	@set -a; . ./.env; set +a; $(PY) -m loftnav.bootstrap

down: check-docker
	@$(COMPOSE) down

smoke: check-env deps
	@$(PY) -m pytest -q tests/smoke

# grafana-smoke (фича 005): HTTP API проверки Grafana поверх поднятого стека (datasource/health/дашборды)
grafana-smoke: check-env deps
	@$(PY) -m pytest -q tests/grafana/integration

# ingestion (фича 002); exit code CLI пробрасывается (2 = частичный успех при битом файле в батче)
ingest: check-env deps
	@test -n "$(FILE)" || { echo "usage: make ingest FILE=<путь>"; exit 2; }
	@set -a; . ./.env; set +a; $(PY) -m loftnav.cli ingest "$(FILE)"

ingest-demo: check-env deps
	@set -a; . ./.env; set +a; $(PY) -m loftnav.cli ingest $(INGEST_DEMO_DIR)

# transform (фича 003): bronze -> silver. ARGS для флагов (--source X / --reprocess X)
transform: check-env deps
	@set -a; . ./.env; set +a; $(PY) -m loftnav.cli transform $(ARGS)

# transform-demo: ingest демо-источников t_avito/t_cian/t_domclick, затем transform в silver
transform-demo: check-env deps
	@set -a; . ./.env; set +a; \
	  $(PY) -m loftnav.cli ingest $(TRANSFORM_DEMO_DIR); \
	  $(PY) -m loftnav.cli transform

# build-gold (фича 004): silver -> gold-витрины + features. ARGS для флагов (--only <mart>)
build-gold: check-env deps
	@set -a; . ./.env; set +a; $(PY) -m loftnav.cli build-gold $(ARGS)

# build-gold-demo: полная цепочка transform-demo -> build-gold (данные для QA 005/006)
build-gold-demo: check-env deps
	@set -a; . ./.env; set +a; \
	  $(PY) -m loftnav.cli ingest $(TRANSFORM_DEMO_DIR); \
	  $(PY) -m loftnav.cli transform; \
	  $(PY) -m loftnav.cli build-gold

# export-dataset (фича 006): gold.apartments_features -> версия датасета в ml-datasets. ARGS для --format
export-dataset: check-env deps
	@set -a; . ./.env; set +a; $(PY) -m loftnav.cli export-dataset $(ARGS)

# export-dataset-demo: полная цепочка build-gold-demo -> export-dataset
export-dataset-demo: check-env deps
	@set -a; . ./.env; set +a; \
	  $(PY) -m loftnav.cli ingest $(TRANSFORM_DEMO_DIR); \
	  $(PY) -m loftnav.cli transform; \
	  $(PY) -m loftnav.cli build-gold; \
	  $(PY) -m loftnav.cli export-dataset

ps:
	@$(COMPOSE) ps

logs:
	@$(COMPOSE) logs -f --tail=100
