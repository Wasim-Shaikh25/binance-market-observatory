# Design

## Durable vs ephemeral

```
queue → DBWriter → SQLite (ops / validate during run; optional persist)
                 → ClickHouse (full raw + normalized; durable)
                 → raw.ndjson.zst (durable evidence)
```

When `database.persist: false` and at least one of CH/archive is enabled, `main`
deletes the SQLite path after graceful shutdown (writer flushed, conn closed).

## ClickHouse schema

MergeTree tables with String decimals. `instrument_snapshots` is denormalized
(`product`, `symbol` columns) — no FK to `instruments`. `coverage_history` close
uses `ALTER TABLE … UPDATE` mutation (acceptable at smoke volume).

All `_NORMALIZERS` kinds + `raw_events` are inserted via batched TabSeparated HTTP.

## Validation

Checklist still runs against the SQLite file **before** delete (same process run),
then compares CH table counts. Report under `validation/report/`.
