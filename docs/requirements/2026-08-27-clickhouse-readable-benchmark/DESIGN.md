# Design

1. `docker run` official `clickhouse/clickhouse-server` (named `bmo-clickhouse`)
2. `research/script/benchmark_clickhouse_load.py`:
   - read SQLite tables
   - CREATE TABLE … ENGINE = MergeTree ORDER BY (…)
   - insert via HTTP interface (stdlib urllib; no new collector dep)
   - prices/qty as String (exact decimal discipline)
   - `raw_events.payload_json` kept as String
3. Measure `system.parts` bytes_on_disk; run sample SELECTs; write REPORT.md
4. Document how to stop/remove the container
