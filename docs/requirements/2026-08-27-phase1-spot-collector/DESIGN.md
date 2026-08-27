# Design: Phase 1 — Spot Collector

**Status:** Not started — this design is a starting point for whoever picks up this
requirement, not a finished spec. Update it as real decisions get made, before writing
the corresponding code.

## Modules

Following `docs/ARCHITECTURE.md` §1's independent-module boundary:

- `connectors/spot/` — owns the Spot WebSocket and REST clients, the depth
  snapshot+sync+resync state machine (per-symbol), and mapping Binance's Spot payloads
  into the shared envelope shape.
- `connectors/spot/instruments.py` — periodic poller for `exchangeInfo`, diffing
  against the last known `instrument_snapshots` row per symbol and writing a new
  snapshot only when something changed.
- `storage/queue.py` — the shared internal queue (in-process to start; no external
  broker needed at this scale).
- `storage/writer.py` — the single DB writer: drains the queue, writes `raw_events`
  plus any applicable normalized row, in one transaction per envelope (or small batch).
- `storage/schema.py` / migrations — SQLite DDL for all Phase 1 tables.
- `health/` — counters exposed by connectors, periodic rollup into `health` and
  `system_events`, plus the 72-hour audit report generator.
- `registry/` — loads the capability registry config and exposes it to connectors.

## Data flow (concrete for Spot)

1. `connectors/spot` opens one WebSocket per stream group (Binance allows combined
   streams; batch by data class per the registry) and one REST poller for
   `exchangeInfo` on its own interval.
2. Each inbound message → envelope (`stream_name, source_endpoint, schema_version,
   observed_at, payload_json`) → pushed to `storage/queue`.
3. Depth messages additionally update per-symbol local book state inside the connector;
   on a detected gap, the connector emits a `system_events` "resync" envelope and
   restarts that symbol's snapshot+sync sequence — this does not block other symbols.
4. `storage/writer` drains the queue, writes `raw_events`, and where the stream maps to
   a normalized table (trades, agg_trades, book_ticker, ticker_24h, candles, depth),
   writes that row in the same transaction.
5. `health/` reads counters + queries the DB on a schedule to populate `health` and,
   at the end of the 24h/72h run, to generate the audit report.

## Depth config (initial)

```yaml
depth:
  enabled: true
  mode: top_n
  top_n: 50
  ranking: quote_volume
  refresh_minutes: 15
```

`refresh_minutes` controls how often the top-N symbol set is recomputed; changing which
symbols are in the set does not require a resync of symbols that stay in it.

## Open decisions (resolve here before/while implementing)

- Exact WebSocket client library and REST client library.
- Batch size / flush interval for the DB writer (throughput vs. write latency).
- Where the capability registry file lives and its exact schema (draft in
  `docs/ARCHITECTURE.md` §4; finalize here).
- Kline intervals collected by default.

## Non-goals

- No other product connectors.
- No query/analysis layer beyond what the audit report needs.
