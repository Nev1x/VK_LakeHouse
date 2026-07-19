# LoftNavigator LakeHouse — управление стеком (фича 001).
# macOS/BSD-совместимо: логика в POSIX-sh рецептах, без GNU-специфики make.
.POSIX:
.PHONY: help up down smoke ps logs deps gen-auth bootstrap check-env check-docker

COMPOSE = docker compose
VENV    = .venv
PY      = $(VENV)/bin/python

help:
	@echo "LoftNavigator LakeHouse — make-цели:"
	@echo "  make up     — поднять стек с нуля (pull -> up -> ожидание healthy)"
	@echo "  make down   — остановить стек (именованные volumes СОХРАНЯЮТСЯ; НЕ -v)"
	@echo "  make smoke  — round-trip smoke: Trino -> Iceberg -> MinIO"
	@echo "  make ps     — статус контейнеров"
	@echo "  make logs   — логи стека (follow)"

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

ps:
	@$(COMPOSE) ps

logs:
	@$(COMPOSE) logs -f --tail=100
