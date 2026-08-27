# Status

**Last updated:** 2026-08-27

## Current phase

**ClickHouse + zstd archive are the durable stores.** SQLite may still be written
during a run for ops/validation, but with `database.persist: false` the `.db` file
is removed after stop when CH and/or archive is enabled.

| Sink | Role |
|---|---|
| ClickHouse | Durable hot / query store (full normalized + raw_events) |
| `raw.ndjson.zst` | Durable raw evidence archive |
| SQLite | Ephemeral ops + optional checklist target (`persist`) |

## Smoke / validate

1. `docker start bmo-clickhouse`
2. `python -m src.main --config config/smoke_settings.yaml --duration-seconds 180`
3. For a checklist run, temporarily set `database.persist: true`, then:
   - `python -m src.validate --db data/market_<run_id>.db --config config/smoke_settings.yaml --out validation/report/BINANCE_DATA_CAPTURE_REPORT.md`
   - `python validation/script/compare_sqlite_clickhouse.py --db … --ch-db bmo_<run_id>`
   - Delete local `data/*.db` when done (or rely on `persist: false`)

## Next

1. Longer clean capture on ClickHouse + archive (24–72h)
2. Optional: validate directly against ClickHouse (no ephemeral SQLite)
