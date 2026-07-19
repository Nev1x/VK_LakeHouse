# tests/agent-evals — execution-grounded eval-корпус (spec 011, roadmap B1)

Курируемые «known-good» задачи для прогонщика `scripts/agent-eval.sh`. Каждая задача измеряется
контрактом SWE-bench: **FAIL→PASS ∧ PASS→PASS** (по exit-коду скрытого `verify.sh`, не по прозе).
Метрика набора — **`% Resolved`**.

## Формат задачи `NNN-slug/`

| Файл | Обяз. | Роль |
|---|---|---|
| `verify.sh` | ✅ | СКРЫТЫЙ судья. Запускается в CWD=рабочая-копия; `exit 0` = решено. Baseline ожидается FAIL (≠0). |
| `instruction.md` | ✅ | «Хотелка» — что сделать. Может нести блок `<!-- eval:apply --> … <!-- /eval:apply -->` с bash-правкой (детерминированный actor). |
| `snapshot.sh` \| `snapshot/` | — | Исходное состояние: скрипт готовит CWD **или** каталог копируется как есть. |
| `regress.sh` | — | Страж PASS→PASS: проверки, что были зелёными, обязаны остаться (`exit 0` после apply). |

## Контракт скоринга

`resolved` ⟺ **baseline verify FAIL** (доказывает, что было что чинить) **И** **final verify PASS**
(∧ `regress.sh` PASS, если есть). `baseline-already-green` не засчитывается (тривиальная задача).
`pass@k` — задача решена, если ≥1 из `k` прогонов resolved. Инвариант-гейт (`pass^k`) — `bash
tests/run-tests.sh` один раз на прогон.

## Запуск

```bash
bash scripts/agent-eval.sh                 # весь корпус, k=3, + инвариант-гейт
bash scripts/agent-eval.sh --k 1 --no-gate # быстрый срез без гейта
bash scripts/agent-eval.sh --out report.json
bash scripts/agent-eval.sh --judge-only    # судить УЖЕ применённое состояние (ручной /pipeline-прогон)
bash scripts/agent-eval.sh --actor '<cmd>' # подать instruction реальному агенту (вне ядра)
```

`% Resolved` пишется в `last-run.json` (generated, gitignored) и показывается плиткой на Flight Deck.

## ⚠️ Траст-граница

`verify.sh`/`snapshot.sh`/`regress.sh`/apply — **произвольный bash с правами оператора, БЕЗ sandbox**.
Ревьюь набор как скрипты; НИКОГДА не гоняй корпус из недоверенного источника. Изоляция прогонщика —
репо-чистота (не мутирует `$ROOT` вне этого каталога), не machine-sandbox.

## Адаптациям

Эти seed-задачи универсальны (без литералов проекта). Заводи свои «known-good» тикеты по тому же
формату; bootstrap не перезаписывает существующие задачи (данные священны).