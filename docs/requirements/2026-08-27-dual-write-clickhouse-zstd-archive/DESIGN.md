# Design

## Writer fan-out

`DBWriter` remains the single queue consumer. After a successful SQLite
transaction (or best-effort alongside), it also:

1. `RawArchiveWriter.append(env)` — one NDJSON line into streaming zstd
2. `ClickHouseSink.enqueue(env)` — batched HTTP inserts

Archive/CH failures log `system_events` (`archive_write_failure` /
`clickhouse_write_failure`) and must not crash the writer or block SQLite.

## Archive line

```json
{"product":"SPOT","symbol":"BTCUSDT","stream_name":"…","source_endpoint":"…",
 "source_type":"websocket","schema_version":"1","observed_at":"…","kind":"trade",
 "payload":{…}}
```

Path: `data/archive_{run_id}/raw.ndjson.zst` (`rotate: none|hour`).

## ClickHouse

- Database `bmo_{run_id}` (template)
- Tables mirror SQLite normalized + `raw_events` (prices as String)
- Batch flush every N envelopes or on shutdown

## Config

```yaml
sinks:
  clickhouse:
    enabled: false
    url: http://127.0.0.1:8123
    user: default
    password: bench
    database: bmo_{run_id}
  raw_archive:
    enabled: false
    path: data/archive_{run_id}/raw.ndjson.zst
    rotate: none
```
