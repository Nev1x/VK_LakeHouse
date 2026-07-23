# Ops Journal — append-only журнал эксплуатации (пишет scripts/ops-log.sh)

DORA-события: `deploy:start|done|failed` · `incident:open|resolved <slug>`; читает `scripts/dora-metrics.sh`.

| ts (UTC) | event | detail |
|---|---|---|
| 2026-07-23T07:56:18Z | deploy:done | sha=14ed0068e4a3db4c5415ddd9fa281b3f3777dde3 rc=0 |
