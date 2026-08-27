# Thesis

This document is the reason this project exists. It is read before any other spec.
If a proposed change cannot be justified from this document, it does not belong here —
see `SCOPE.md` for the enforced boundary.

## 1. What this project is

Binance Market Observatory is a **public-data collector**. It connects to Binance's
public REST and WebSocket APIs — no API key, no account, no authenticated user-data
streams — and records everything those public interfaces expose, as close to the wire
format as possible, into a queryable SQL database.

It is infrastructure, not intelligence. It answers "what did the market do and did we
actually record it correctly", never "what should we trade".

## 2. Why it exists

Every serious market-microstructure or trading-behavior experiment starts by wishing it
had raw historical data it doesn't have, in a shape it can trust. The recurring failure
mode is building the analysis and the collector at the same time: the collector gets
bent to fit whatever the first analysis needed, loses raw fidelity, and can't support
the next question.

This project inverts that: build a collector with no analytical opinion, that preserves
the raw exchange data faithfully and durably, so that *any* future experiment (behavioral
research, backtests, anomaly detection, whatever comes next) can be built on top of a
dataset that already exists and is already trustworthy. The observatory's job ends at
"the data is in the database, verified, and Binance's own state is reconstructable from
it." Everything past that point is a different project.

## 3. Product scope

| Binance product        | In scope | Notes |
|-------------------------|:--------:|-------|
| Spot                     | ✅ | Primary product; also carries margin-tradable metadata (see §5.1) |
| Margin                   | ✅ | Represented as **metadata on Spot instruments**, not a separate market-data pipeline (see §5.1) |
| USDⓈ-M Futures           | ✅ | Own connector: trades, depth, funding, open interest, mark/index price, liquidations |
| COIN-M Futures           | ✅ | Own connector, same data classes as USDⓈ-M where the API exposes them |
| Options                  | ✅ | Own connector; scope follows whatever the current public API/stream surface supports |

No authenticated account/user-data collection of any kind. Binance's user-data streams
require API keys; this project never asks for one.

```
BINANCE
   │
   ├── SPOT ── margin_tradable metadata
   ├── MARGIN (folded into Spot instrument metadata, not a separate collector)
   ├── USDⓈ-M FUTURES
   ├── COIN-M FUTURES
   └── OPTIONS
         │
         ▼
   PUBLIC DATA COLLECTOR
         │
         ▼
   RAW SQL DATA (SQLite, WAL, single writer)
```

For each in-scope product, the collector captures the **maximum relevant public market
data** that product's API/stream surface makes available — not just trades, but every
public data class that product exposes (order book, funding, open interest,
liquidations, mark/index price, klines, ticker statistics, exchange/instrument
metadata) as applicable to that product.

## 4. Core principles

These are non-negotiable defaults for every design decision in this project:

1. **Public data only.** No API keys, no authenticated endpoints, no user-data streams.
2. **Raw fidelity first.** Every payload is stored close to as-received before any
   normalization happens. Normalized tables are a convenience view on top of the raw
   record, never a replacement for it.
3. **Exact numbers.** Prices, quantities, and any exchange-supplied decimal value are
   stored as text/canonical decimal strings. Floats are never used for values that will
   later be compared, summed, or diffed — floating-point rounding has no place in the
   raw layer.
4. **SQL, not files.** The dataset lives in a real SQL database (SQLite to start,
   WAL mode, single writer) so it is queryable, indexable, and auditable from day one.
5. **Correctness over completeness.** A gap the system detected and recorded is fine.
   A gap the system didn't notice is the one failure mode this project cannot tolerate.
   Health/audit instrumentation is not optional polish — it is core scope.
6. **No trading intelligence inside the collector.** No ML, no strategies, no signal
   generation, no execution, no backtesting. That is explicitly a different, later
   project that will consume this one's output. See `SCOPE.md`.
7. **The system evolves; the schema shouldn't have to.** Binance's API surface changes
   over time. Prefer a small, explicit capability registry and versioned raw payloads
   over hard-coded assumptions scattered through the codebase (see §7).

## 5. Data model decisions

### 5.1 Instruments vs. instrument snapshots

An instrument's identity (`exchange`, `product`, `symbol`) is stable. Its trading rules
(tick size, step size, min notional, margin-tradable status, ...) are not — Binance
changes them over time, and losing that history loses the ability to correctly interpret
old trades. So the model is split:

- `instruments` — current/static identity. One row per `(exchange, product, symbol)`.
- `instrument_snapshots` — historical metadata, one row per observation:
  `instrument_id, observed_at, status, tick_size, step_size, min_qty, min_notional,
  margin_tradable, payload_json`.

Margin is represented here: `margin_tradable` (and related margin fields) is a column on
a Spot instrument's snapshot, not a parallel "margin market data" pipeline. Margin does
not have its own order book or trade stream distinct from Spot's — collecting it twice
would be duplicate ingestion of the same market for no benefit.

### 5.2 Raw events as the safety net

`raw_events` stores the exchange payload essentially as received
(`payload_json TEXT NOT NULL`, plus `stream_name`, `source_endpoint`, `schema_version`,
`observed_at`) independently of whatever normalized tables exist. When a future
experiment needs a field nobody thought to normalize, it's recoverable from
`raw_events` without re-collecting history that can never be re-collected (the market
already moved on). This table is kept even after normalized tables mature — it is not
a temporary bootstrap measure.

### 5.3 Raw trade stream

The raw `@trade` stream is stored as **raw exchange trade observations** — not "ground
truth". It's the exchange's own record of what it says happened on that channel, which
is exactly what this project wants, but calling it "ground truth" overstates what a
single public stream can guarantee (dropped connections, exchange-side dedup behavior,
etc. are still possible). Fields preserved: `trade_id, event_time, trade_time, price,
quantity, buyer_maker`, plus the standard raw-event envelope.

### 5.4 Order book depth

Depth is maintained by Binance's documented synchronization procedure, not simplified:

```
REST snapshot
     │
     ▼
WebSocket depth updates
     │
     ▼
validate update IDs (must chain from snapshot's lastUpdateId with no gaps)
     │
     ▼
maintain local book
     │
     ▼
gap or desync detected? ──yes──▶ discard local book ──▶ re-snapshot ──▶ resume
     │no
     ▼
keep applying updates
```

Missed events require restarting local book reconstruction — this is Binance's own
documented behavior, and the collector must treat it as a first-class case, not an edge
case discovered in production.

Depth collection breadth (which symbols get full order-book depth vs. lighter-weight
streams like trades/bookTicker/ticker) is **configuration, not a hard-coded symbol
list**, and defaults to a rotating/rankable universe rather than a fixed "top N by
market cap" list — so that large-cap symbols (BTC, ETH) don't structurally dominate the
research dataset just because they're large:

```yaml
depth:
  enabled: true
  mode: top_n
  top_n: 50
  ranking: quote_volume
  refresh_minutes: 15
```

Trades, bookTicker, and ticker are collected for the broader symbol universe regardless
of whether a symbol is currently in the depth top-N.

## 6. Storage architecture

```
many WebSocket/REST connectors (one per product/data-class)
              │
              ▼
      one internal queue
              │
              ▼
       one DB writer
              │
              ▼
      SQLite (WAL mode)
```

SQLite with WAL and a single writer is the right starting point — simple, durable,
zero infrastructure to operate. Optional dual sinks (config `sinks:`) can also
write the same envelopes to **ClickHouse** (hot/query) and a streaming
**NDJSON+zstd** raw archive (evidence) while SQLite remains enabled for
comparison. Migration off SQLite is decided only after measured comparison.
If volume outgrows SQLite alone, the path is SQLite → dual-write benchmark →
ClickHouse + raw archive (Parquet optional later). Multiple concurrent SQLite
writers are never introduced; the queue + single-writer boundary is fixed.

## 7. Capability registry

Binance's documented API surface changes over time and varies per product. Rather than
encoding assumptions about what's available where throughout the codebase, the project
maintains a small declarative registry:

```yaml
- product: SPOT
  data_type: trade
  source: websocket
  stream_name: <symbol>@trade
  poll_interval: null
  symbol_scope: all
  enabled: true
```

When Binance adds, removes, or changes an endpoint/stream, the fix is a registry/config
and connector-level change, not a database redesign.

## 8. Health and correctness, not just row counts

A 72-hour clean-run audit is required before a product's collector is considered
trustworthy, and the audit is written *before* collection starts, not after. It answers
"did we actually capture the market", not "does the database contain rows". At minimum
it reports: symbol coverage, per-stream event counts, timestamp gaps, duplicate counts,
sequence/update-ID gaps, depth resync counts, WebSocket reconnect counts, REST failure
counts, stale-stream detection, database write failures, and storage growth.

## 9. Build order

Failures must be isolated to the product being added, never cascade into products
already running clean.

1. **Phase 1 — Spot**: instruments (+ margin metadata), trades, aggTrades, bookTicker,
   ticker, candles, depth, health/audit, reconnect/resync. Run clean for 24h minimum.
2. **Phase 2 — USDⓈ-M Futures**: added only after Phase 1 is stable.
3. **Phase 3 — COIN-M Futures**.
4. **Phase 4 — Options**: scope confirmed against Binance's current public
   API/stream capabilities at implementation time (this surface is the most likely to
   have changed since this thesis was written).
5. Margin is not a phase — it ships as part of Phase 1 (see §5.1).

## 10. What this project deliberately will never become

See `SCOPE.md` for the enforced list. In one line: this project stops at "the market's
public data is durably and verifiably in the database." Anything that interprets,
predicts, or acts on that data is a separate, later project consuming this one's output.

## 11. Accepted limitations (do not chase)

**The absence of a stable public machine-readable Binance announcements feed is an
accepted limitation and does not constitute a failure of the Market Observatory.
Options WebSocket availability is environment-dependent; where the public REST
interface provides the required information, REST collection is acceptable and the
project must not depend on Options WebSocket availability.**

Operational corollary: after gap-fill + coverage_history land and a multi-product
validation passes, the next step is a continuous clean run and freeze — not more
collector features for their own sake.
