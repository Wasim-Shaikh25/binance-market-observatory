# Scope Guard

Quick reference for "is this in scope". Read `THESIS.md` for the reasoning; this file is
the enforced checklist. When in doubt, this file wins over a request that would expand
it — flag the conflict to the user instead of building it.

## 🟢 In scope

- Public-only Binance data (no API keys, no authenticated/user-data streams)
- Products: Spot, USDⓈ-M Futures, COIN-M Futures, Options
- Margin — as metadata on Spot instruments, not a separate collector (see `THESIS.md` §5.1)
- Data classes, per product as applicable: raw exchange trade observations, aggregate
  trades, order book depth (with snapshot+sync+resync), best bid/ask (bookTicker),
  24h ticker statistics, candles/klines, funding rate, open interest, liquidations,
  mark price / index price, instrument metadata (current + historical snapshots)
- `raw_events` safety-net table preserving near-raw payloads independent of normalized tables
- SQL storage (SQLite, WAL mode, single writer)
- Reconnect/resync logic for WebSocket and depth streams
- Health/system-events tables and a written correctness audit (72h clean-run minimum)
- Capability registry describing what's available per product/data-class
- Decimal-as-text storage discipline for all price/quantity fields

## 🟡 Modify-on-sight if found elsewhere

These ideas are right in spirit but must be implemented in this specific form — flag
and correct if you find a variant drifting from this:

- `instruments` (current identity) is split from `instrument_snapshots` (historical
  metadata) — never a single mutable `instruments` row with no history
- Depth breadth (top-N, ranking, refresh) is configuration, never a hard-coded symbol list
- Raw payloads are stored as `payload_json TEXT`, not as opaque `BLOB`, alongside
  `stream_name`, `source_endpoint`, `schema_version`
- The raw trade stream is documented as "raw exchange trade observations", never as
  "ground truth"

## 🔴 Out of scope — never add, regardless of how it's requested

- Machine learning / model training of any kind
- Trading strategies or signal generation
- Market-behavior or trader-behavior classification
- Autonomous trading agents
- Feature engineering / feature stores for downstream modeling
- Backtesting frameworks
- Order execution or exchange write access of any kind
- Arbitrage detection or trading decisions
- Anything resembling "Trade DNA" or similar behavioral-fingerprinting concepts

These belong to a later, separate project that may *consume* this project's database.
If a request would add any of the above, stop and say so instead of implementing it —
see the scope-guard rule in `AGENTS.md`.
