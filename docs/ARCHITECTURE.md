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
                                        │
                                        ▼
                            SQLite (WAL mode) — the database
                                        │
                                        ▼
                          Health / audit subsystem (reads DB,
                          writes to health & system_events tables)
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
   transactions against SQLite. It writes the raw envelope to `raw_events` and, where a
   normalized table exists for that data class, writes the normalized row in the same
   transaction.
5. The health/audit subsystem runs independently (scheduled), reading from the DB and
   from connector-exposed counters, and writes rollups to `health`/`system_events`.

## 3. Storage layer

- Engine: SQLite, WAL mode, single writer enforced by routing all writes through the
  DB writer component (never opened for write from more than one process/thread).
- Migration path if/when SQLite is outgrown: benchmark first, then consider
  PostgreSQL/ClickHouse/Parquet — not decided speculatively.

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
- `funding_rate`, `open_interest`, `liquidations`, `mark_price` — futures/options data
  classes, present only for products whose API exposes them
- `health` — per-connector/per-stream rollups (event counts, gap counts, reconnects, etc.)
- `system_events` — reconnects, resyncs, REST failures, DB write failures

All price/quantity/decimal columns are `TEXT` holding canonical decimal strings, never
floating point.

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

## 6. Tech stack (locked, as of the Phase 1 implementation)

- Language: Python 3.11+.
- Networking: `aiohttp` for both REST (`RestClient`) and WebSocket (`ws_messages`) --
  one dependency covers both, and its `ClientSession` gives every connector a shared
  connection pool.
- Storage: `aiosqlite`, WAL mode, `synchronous=NORMAL`, single writer (`DBWriter`).
- Config: YAML (`pyyaml`) for the capability registry (`config/settings.yaml`), loaded
  into typed dataclasses in `src/config.py`.
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
│       └── options.py             # raw-fidelity-only connector (see its docstring)
├── config/
│   └── settings.yaml       # the capability registry
├── data/                    # SQLite database lives here (gitignored)
└── tests/
    ├── mock_binance.py      # local Binance protocol stand-in
    ├── test_integration_spot.py   # full pipeline test against the mock
    ├── test_main_and_audit.py     # entrypoint + audit report smoke test
    └── test_*.py                   # unit tests (ratelimit, depth_sync, storage, parsers)
```

Not yet built: a live 72-hour run against real Binance (blocked in this sandbox --
see `STATUS.md`), and normalized tables for Options (raw-fidelity only until its wire
format is confirmed against live docs).
