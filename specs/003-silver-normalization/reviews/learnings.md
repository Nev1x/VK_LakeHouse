# Learnings — 003-silver-normalization

## stage-1
- **Deviations:** сжатый состав (2 субагента, делегированный режим) — как в 002.
- **Interpretations:** «универсальный маппинг-конфиг» intent → закрытый набор именованных
  примитивов, НЕ произвольные выражения (security/тестируемость).
- **Tradeoffs:** cross-source дедуп честно вынесен из scope (false positives опаснее дублей);
  MERGE выбран при условии spike-подтверждения на Trino 483.

## stage-2
- **Learnings:** чтение исходников зависимостей (trino dbapi) на аудите дешевле spike'ов —
  Decimal-bind и EXECUTE IMMEDIATE подтверждены без запуска; CRITICAL-класс «рефакторинг
  общего модуля ломает существующий call-site» ловится только перечислением call-site'ов.
- **Deviations:** нет (сжатый состав как в 002).

## stage-3
- **Learnings:** восстановление после обрыва — только по факту (git/pytest), не по памяти
  агента (ложная память о готовом файле); терминальность partial-статуса для transform
  обязательна (иначе повтор копит rejects); MERGE USING VALUES требует типизации через CAST
  при all-NULL колонках.
- **Deviations:** отдельные демо-источники (фикстуры 002 не подходят под обязательные поля);
  length-prefix в id-хэше.

## stage-3 (fix-цикл после stage-4)
- **Learnings:** ReDoS-защита по ДЛИНЕ входа не закрывает catastrophic backtracking на коротком
  значении — нужен лимит ВРЕМЕНИ; CPython 3.12 `re` реагирует на SIGALRM во время matching
  (эмпирически подтверждено kulibin до реализации — I-13), поэтому setitimer-watchdog работает
  без процессной изоляции; reprocess обязан чистить quarantine симметрично silver (иначе дубли).
