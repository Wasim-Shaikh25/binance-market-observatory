# Requirements: ClickHouse install + one-DB readable size benchmark

**Opened:** 2026-08-27  
**Why:** Measure ClickHouse compressed size on the same smoke DB used for the
Parquet benchmark, and prove rows remain SQL-queryable. No live-collector rewrite.

## In scope

- Run ClickHouse via Docker on this host
- Load normalized high-volume tables + `raw_events` (payload retained) from one SQLite DB
- Report bytes_on_disk vs SQLite / Parquet / gzip
- Prove readability with sample SELECT queries in the report
- Research script under `research/script/`; report under `research/report/`

## Out of scope

- Replacing SQLite in `src/main.py`
- Permanent production ClickHouse ops / AIOM
- Deleting raw payloads
