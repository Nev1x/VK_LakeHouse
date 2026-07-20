# Learnings — 005-grafana-dashboards

## stage-1
- **Interpretations:** «дашборды показывают живые данные» → build-gold-demo как seed перед
  приёмкой; чистый up без данных = «No data» (не провал).
- **Deviations:** сжатый состав (делегированный); System Analyst делал внешние запросы для id
  плагина (единственные не-репо факты, помечены — сверить эмпирически на stage-2/3).
- **Open questions:** точные auth-поля datasource-плагина и синтаксис $__env под Grafana 12.3.8
  — spike stage-3 (не гадать).

## stage-2
- **Learnings:** pre-commit secret-скан ловит только известные форматы токенов — generic-пароль
  в provisioning не поймает; enforcement «нет plaintext» должен быть в собственном unit-тесте,
  не в доверии хуку; Grafana provisioning env-синтаксис — $VAR/${VAR}, не $__env{} (частая
  ошибка); дашборд-панели по растущему журналу обязаны быть bounded (I-15) — time-picker+LIMIT.
- **Deviations:** Constitution прогнан дважды (I-15 MUST-FLAG закрыт правкой); сжатый состав.

## stage-3 (fix-цикл после stage-4)
- **Learnings:** /api/plugins/<id>/settings.enabled для datasource-плагинов Grafana = app-toggle
  (false), не «работоспособность»; надёжный сигнал — агрегатный /api/plugins + datasource
  health OK; тест не должен полагаться на квирк-эндпоинт (ни ложной гарантии, ни ложного FAIL).
- **Deviations:** browser-QA (semiglazka) BLOCKED — Playwright MCP не подключён в runtime;
  documented gap (принцип 4: честный gap-отчёт, не симуляция), покрытие через API/JSON.
