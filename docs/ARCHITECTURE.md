# Architecture

Living document — keep this in sync with the code. Whenever a change alters a module
boundary, a table shape, or a data flow described here, update this file in the same
change (see `AGENTS.md`, "docs sync" rule).

## 1. Component overview

```
┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│   Spot      │  │  USDⓈ-M     │  │  COIN-M     │  │  Options    │  │  Instrument │
│  connector  │  │  connector  │  │  connector  │  │  connector  │  │  metadata   │
│             │  │             │  │             │  │             │  │  poller     │
└──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘
       │                │                │                │                │
       └────────────────┴────────────────┴────────────────┴────────────────┘
                                        │
                                        ▼
                              internal event queue
                                        │
                                        ▼
                                  DB writer (single)
                     ┌─────────────┼─────────────────┐
                     ▼             ▼                 ▼
              SQLite (WAL)*  ClickHouse         raw.ndjson.zst
              ephemeral ops   durable hot        durable archive

\* SQLite remains for in-run ops (gap-fill reads, system_events) and optional
  checklist validation. With `database.persist: false` and CH/archive enabled,
  the `.db` file is deleted after graceful stop — ClickHouse + archive are
  durable.
```

Each product connector is an **independent module**: it owns its own WebSocket/REST
clients, its own reconnect and depth-resync logic, and its own mapping from Binance's
wire format to the shared internal event shape. Connectors never import each other and
never talk to the database directly. The only thing that ties them together is:

1. The **capability registry** (config) that declares what each connector should collect.
2. The **internal queue** and the shared **event envelope** shape they emit into it.
3. The **raw-event contract**: every connector, regardless of product, must emit an
   envelope carrying `stream_name`, `source_endpoint`, `schema_version`, `observed_at`,
   and `payload_json`, so the DB writer and `raw_events` table stay product-agnostic.

This is the "independent but tightly connected" boundary: independence in
implementation, tight coupling only through these three shared, explicit contracts —
never through reaching into another connector's internals.

## 2. Data flow

1. A connector receives a message (WebSocket push or REST poll response).
2. It wraps the raw payload in the shared envelope and pushes it onto the internal queue.
3. It also performs any product-specific stateful validation it owns (depth update-ID
   continuity, sequence gap detection) and emits health/system events on failure.
4. The DB writer drains the queue and is the only component that opens write
   transactions against SQLite (when used). It writes the raw envelope to `raw_events` and, where a
   normalized table exists for that data class, writes the normalized row in the same
   transaction. Optional dual sinks flush the same envelopes to ClickHouse and the
   zstd NDJSON archive.
5. The health/audit subsystem runs independently (scheduled), reading from the DB and
   from connector-exposed counters, and writes rollups to `health`/`system_events`.

## 3. Storage layer

- Primary durable store: **ClickHouse** (full normalized mirrors + `raw_events`,
  prices as String) plus streaming **NDJSON+zstd** raw archive.
- SQLite: WAL mode, single writer; used for in-run ops and optional validation.
  Not retained when `database.persist: false` and a durable sink is enabled.
- Migration path if/when needed: already on ClickHouse for hot data; Parquet remains
  an optional cold-export research path only — not on the live write path.

### 3.1 Core tables (shape, not final DDL — DDL lives with the implementing requirement)

- `raw_events` — `id, stream_name, source_endpoint, schema_version, observed_at, payload_json`
- `instruments` — `id, exchange, product, symbol` (current identity, unique per triple)
- `instrument_snapshots` — `id, instrument_id, observed_at, status, tick_size, step_size,
  min_qty, min_notional, margin_tradable, payload_json`
- `trades` — raw exchange trade observations: `trade_id, symbol, event_time, trade_time,
  price, quantity, buyer_maker`
- `agg_trades` — aggregate trade stream, Binance's aggregated-taker-order shape
- `book_ticker` — best bid/ask per symbol
- `ticker_24h` — rolling 24h statistics
- `candles` — klines per interval
- `depth_snapshots` / `depth_updates` — order book state per §5.4 of `THESIS.md`
- `funding_rate`, `open_interest`, `liquidations`, `mark_price` — futures data classes,
  present only for products whose API exposes them
- `futures_positioning` — public long/short positioning ratios (global account,
  top-trader account, top-trader position, taker buy/sell), stored raw with no
  interpretation: `metric`, `value`, `observation_time`, `source_endpoint`, `payload_json`
- `symbol_coverage` — an explicit, queryable record of which tier (`BROAD` vs
  `HIGH_RESOLUTION`) each symbol had at each point in time, written every
  depth-refresh cycle for the whole universe, not just the depth-tracked subset (see
  §5.5)
- `health` — per-connector/per-stream rollups (event counts, gap counts, reconnects, etc.)
- `system_events` — reconnects, resyncs, REST failures, DB write failures

All price/quantity/decimal columns are `TEXT` holding canonical decimal strings, never
floating point. Every table that receives a Binance-supplied timestamp for its data
point stores it in a dedicated column, distinct from `observed_at` (this collector's
own receive/poll time) -- e.g. `open_interest.observation_time` is when Binance
measured the value, not when this collector happened to poll it. The one exception is
`book_ticker`: Binance's payload for that stream carries no timestamp at all (only an
update ID), which is documented in the schema as an upstream limitation, not an
oversight.

## 4. Capability registry

A config-driven registry (see `THESIS.md` §7) declares, per product and data class,
whether it's sourced from REST or WebSocket, the stream/endpoint name, poll interval
(if polled), symbol scope, and whether it's currently enabled. Connectors read this
registry at startup and drive their behavior from it rather than hard-coded per-product
branches. When Binance changes an API surface, the fix should land in the registry
and/or a single connector, never as a ripple across the schema.

## 5. Depth synchronization state machine

See `THESIS.md` §5.4 for the full diagram and reasoning. Implementation note: this is
per-symbol state (each symbol being depth-tracked has its own snapshot/update-ID/local
book state), not a single global state machine.

## 5.5 Two-tier coverage

Only the depth-tracked top-N symbols get full order book depth (and, for futures, open
interest and positioning data) -- the rest of the universe still gets the cheap feeds
(trades, bookTicker, ticker, candles) via the broad streams. This is a deliberate
compute/storage tradeoff, but it must never quietly bias what gets studied: a future
finding of "nothing interesting happens in small-cap symbols" must be distinguishable
from "small-cap symbols never got instrumented well enough to tell." `symbol_coverage`
makes the tier assignment an explicit, queryable fact recorded every depth-refresh
cycle (`connectors/market.py`'s `_record_coverage_tiers`), for every universe symbol,
not just the ones currently in the high-resolution set.

## 6. Tech stack (locked, as of the Phase 1 implementation)

- Language: Python 3.11+.
- Networking: `aiohttp` for both REST (`RestClient`) and WebSocket (`ws_messages`) --
  one dependency covers both, and its `ClientSession` gives every connector a shared
  connection pool.
- Storage: `aiosqlite`, WAL mode, `synchronous=NORMAL`, single writer (`DBWriter`).
- Config: YAML (`pyyaml`) for the capability registry (`config/settings.yaml`), loaded
  into typed dataclasses in `src/config.py`. USDS-M WebSocket base URL must be
  `wss://fstream.binancefuture.com` (not `fstream.binance.com`, which can silently
  omit aggTrade/ticker/kline/markPrice/forceOrder while still delivering
  trade+bookTicker — verified live 2026-08-27).
- Validation/research outputs: `validation/{script,report}/` and
  `research/{script,report}/` per `AGENTS.md` rule 8.
- Tests: `pytest` + `pytest-asyncio`, plus a local protocol-faithful mock of Binance's
  REST/WebSocket API (`tests/mock_binance.py`) used because this project's development
  sandbox cannot reach Binance's real servers (see `STATUS.md`) -- a live run against
  Binance is still required before any phase is considered done.

## 7. Repository layout (as built)

```
binance-market-observatory/
├── README.md
├── AGENTS.md
├── CHANGELOG.md
├── STATUS.md
├── requirements.txt
├── requirements-dev.txt
├── pytest.ini
├── docs/
│   ├── THESIS.md
│   ├── SCOPE.md
│   ├── ARCHITECTURE.md
│   └── requirements/
│       └── <YYYY-MM-DD>-<slug>/
│           ├── REQUIREMENTS.md
│           ├── DESIGN.md
│           ├── TASKS.md
│           └── TRACKER.md
├── src/
│   ├── config.py          # capability registry loader (YAML -> dataclasses)
│   ├── models.py          # Envelope contract, taker_side derivation
│   ├── schema.py           # SQLite DDL
│   ├── storage.py          # DBWriter: the single writer, raw + normalized inserts
│   ├── ratelimit.py         # RestWeightLimiter, WsConnectionLimiter
│   ├── binance_client.py    # RestClient, ws_messages() (reconnect/backoff)
│   ├── depth_sync.py         # DepthSyncTracker: snapshot+sync+resync state machine
│   ├── health.py             # audit report generator
│   ├── audit.py               # CLI: generate the audit report
│   ├── main.py                 # entrypoint: registry -> connectors -> queue -> writer
│   └── connectors/
│       ├── common.py            # shared parsers (spot/usdm/coinm wire shapes match)
│       ├── market.py             # generic connector driving spot/usdm/coinm
│       ├── spot.py, usdm.py, coinm.py  # per-product REST paths + futures flags
│       ├── options.py             # Options REST primary + WS best-effort
│       └── system_status.py       # public /sapi/v1/system/status → exchange_status
├── config/
│   └── settings.yaml       # the capability registry
├── data/                    # SQLite database lives here (gitignored)
├── validation/              # validation script + report outputs
└── tests/
    ├── mock_binance.py      # local Binance protocol stand-in
    ├── test_integration_spot.py   # full pipeline test against the mock
    ├── test_main_and_audit.py     # entrypoint + audit report smoke test
    └── test_*.py                   # unit tests (ratelimit, depth_sync, storage, parsers)
```

Normalized Options tables: `options_mark` (IV/greeks as TEXT), `options_index`.
Options depth/OI reuse `depth_snapshots` / `open_interest` via REST polls.
Exchange-wide: `exchange_status`. Provenance: `raw_events.source_type`
(`websocket` | `rest_poll` | `rest_backfill` | `internal`).
Gap-fill: `src/gap_fill.py` recovers public aggTrades/klines holes into the queue
with `rest_backfill` (never overwrites live UNIQUE rows); jobs in `gap_fill_jobs`.
Coverage: `symbol_coverage` snapshots + `coverage_history` open/closed DEPTH
intervals with reasons. A literal 72-hour clean run is an operational step
(see `STATUS.md`) — not a missing connector.
