# Requirements: Dual-write SQLite + ClickHouse + zstd NDJSON archive

**Opened:** 2026-08-27  
**Why:** Keep SQLite for comparison while adding the target sinks: ClickHouse
(hot/query) and streaming NDJSON+zstd raw archive (evidence). Remove SQLite
only after a measured comparison.

## In scope

1. Config for optional sinks (`sinks.clickhouse`, `sinks.raw_archive`)
2. Streaming zstd NDJSON archive (one file per run by default; optional hourly rotate)
3. Live ClickHouse dual-write of `raw_events` + same normalized kinds as SQLite
4. SQLite remains default-on
5. Smoke config can enable sinks; tests for archive + config
6. Docs: THESIS/ARCHITECTURE note migration path; CHANGELOG/STATUS

## Out of scope

- Deleting SQLite yet
- Parquet
- AIOM
