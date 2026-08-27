# Status

**Last updated:** 2026-08-27

## Current phase

**Dual-write mode available:** SQLite (primary) + optional ClickHouse + zstd
NDJSON archive. Compare both after a run; remove SQLite only after that.

| Sink | Role now |
|---|---|
| SQLite | Still primary / comparison baseline |
| ClickHouse | Optional live dual-write (hot/query) |
| `raw.ndjson.zst` | Optional streaming raw evidence archive |

## Enable dual-write

1. `docker start bmo-clickhouse` (user `default` / password `bench`)
2. Set in config (`config/smoke_settings.yaml` already on):
   - `sinks.clickhouse.enabled: true`
   - `sinks.raw_archive.enabled: true`
3. `python -m src.main --config config/smoke_settings.yaml`
4. Stop with **Ctrl+C** (graceful) so CH batch + archive flush
5. Compare: `python validation/script/compare_sqlite_clickhouse.py --db … --ch-db …`

## Next

1. Longer dual-write capture → compare sizes/counts
2. If CH + archive look good → drop SQLite in a follow-up change
3. Then 24–72h clean run on the chosen store
