# Ops Journal — append-only журнал эксплуатации (пишет scripts/ops-log.sh)

DORA-события: `deploy:start|done|failed` · `incident:open|resolved <slug>`; читает `scripts/dora-metrics.sh`.

| ts (UTC) | event | detail |
|---|---|---|
| 2026-07-23T07:56:18Z | deploy:done | sha=14ed0068e4a3db4c5415ddd9fa281b3f3777dde3 rc=0 |
| 2026-07-23T08:05:35Z | deploy:done | sha=29fce9d8c202c7d5ac4848b52b5ea5e500b162ba rc=0 |
| 2026-07-24T08:04:24Z | deploy:failed | sha=f3c807d73f7ed07dbac8762a5559c8e532b1c558 rc=1 |
