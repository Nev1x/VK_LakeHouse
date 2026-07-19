# Learnings — 001-lakehouse-infra

## stage-1

- **Interpretations:**
  - Шаблон стадии упоминает Go/gRPC/NATS/React — это нелокализованный bootstrap-текст; трактовал
    роли субагентов через реальный стек проекта (team.params: Python/Trino/Iceberg/MinIO/Grafana).
  - «Bootstrap bucket'ов (warehouse, слои raw/bronze/silver/gold)» из intent трактован как:
    bucket'ы raw/warehouse/ml-datasets + Iceberg-namespace'ы bronze/silver/gold (слои managed-зоны
    живут в warehouse как схемы каталога, а не как отдельные bucket'ы/префиксы).
  - Субагентов спавнил как general-purpose с ролью в промпте: стабов system-analyst/hard-critic
    в agents нет, а файлы агентов владелец велел не трогать.
- **Deviations:**
  - В spec добавлены FR-011 (pyproject уже в 001) и .gitignore, которых не было в intent:
    без них контрактная команда `pytest -q && ruff check .` красная на каждом коммите (exit 5),
    а .env рискует уехать в git.
- **Tradeoffs:**
  - Grafana оставлена в 001 вопреки CUT Hard Critic — зафиксировано как спорное решение и
    вынесено владельцу на гейт (FR-14); цена ошибки мала в обе стороны.
  - Порты Trino/MinIO публикуются на 127.0.0.1 ради host-доступа smoke и будущего CLI 002 —
    расширение относительно «data_net не публикуется», обосновано периметром=машина; на гейт.
- **Open questions:**
  - Точные пины версий образов (Trino ↔ JDBC catalog совместимость) — задача stage-2 плана.

## stage-2

- **Interpretations:**
  - Шаблонные роли AI/Frontend Reviewer не применимы (нет AI-сервиса и фронта в 001) — заменены
    на Compatibility/Infra Reviewer (версии/грабли Trino+Iceberg+MinIO); это дало 0 CRIT, но
    самый практичный список подводных камней.
  - MUST-FLAG'и устава закрыты правками спеки ДО гейта (по правилу блокировки
    constitution-check), затем повторный свежий прогон гейта (I-13), а не самооценка.
- **Deviations:**
  - Constitution Gate прогнан дважды (до/после правок) — шаблон стадии предусматривает один
    прогон; повтор был необходим, чтобы триплет гейта отражал реальное состояние спеки.
- **Tradeoffs:**
  - Trino auth через allow-insecure-over-http (пароль по HTTP на loopback) вместо полного TLS —
    цена MVP, задокументирована как Known Risk 4.
  - Ратификация перечня портов перенесена на Approve владельца (механика гейта), а не отдельная
    поправка устава — I-1 сам предусматривает «явно решённые владельцем entrypoints».
- **Open questions:**
  - Точные теги образов — только на шаге 1 stage-3 (сверка Docker Hub + доки релиза).

## stage-3

- **Interpretations:**
  - «Hiring недостающих агентов» шаблона пропущен: владелец велел использовать существующих
    агентов по назначению — кодил kulibin, файлы агентов не создавались/не правились.
- **Deviations:**
  - FR-015: password-over-HTTP невозможен by design в Trino → dual-port HTTPS:8443; спека
    уточнена пометкой stage-3 (WHAT сохранён: Trino под паролем, перечень портов не изменился).
  - Служебные таблицы JDBC-каталога созданы pre-init SQL (Iceberg 1.11 не даёт init из Trino).
- **Tradeoffs:**
  - Self-signed TLS + verify=False у клиентов — цена auth на loopback-MVP; внутренний HTTP
    беспарольный в пределах compose-сетей.
- **Open questions:**
  - Ужесточение internal-Trino и least-privilege MinIO — отдельные фичи бэклога?
