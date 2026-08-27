# Requirements: One-file storage format benchmark

**Opened:** 2026-08-27  
**Why:** Measure actual compression on a real observatory DB before any
ClickHouse/Parquet migration. No collector rewrite. No AIOM.

## In scope

- Research script: one SQLite DB → size of SQLite, raw NDJSON (+gzip), Parquet+ZSTD
  for high-volume normalized tables + optional raw payloads column
- Report under `research/report/`
- ClickHouse: measure only if a client is installed; otherwise document N/A

## Out of scope

- Migrating the live collector off SQLite
- Installing/operating ClickHouse in this change
- Deleting raw payloads
- AIOM / trading / ML
