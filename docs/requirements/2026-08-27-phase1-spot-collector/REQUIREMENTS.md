# Requirement: Phase 1 — Spot Collector

**Opened:** 2026-08-27
**Status:** Not started

## Why

Per `docs/THESIS.md` §9 (build order), Spot is the first product implemented, run clean
for a minimum of 24 hours before any other product is added. This isolates failures to
one product while the connector/queue/writer/health foundation is proven out.

## What is needed

A working Spot collector covering:

- **Instrument metadata**: `instruments` + `instrument_snapshots`, including
  `margin_tradable` and other margin-relevant fields as Spot instrument metadata
  (not a separate margin collector — see `THESIS.md` §5.1).
- **Raw trade stream** (`@trade`) → `raw_events` + normalized `trades`.
- **Aggregate trades** (`@aggTrade`) → `raw_events` + normalized `agg_trades`.
- **Best bid/ask** (`@bookTicker`) → `raw_events` + normalized `book_ticker`.
- **24h ticker statistics** → `raw_events` + normalized `ticker_24h`.
- **Candles/klines** (configurable intervals) → `raw_events` + normalized `candles`.
- **Order book depth** with snapshot + WebSocket sync + gap-detection resync per
  `THESIS.md` §5.4, breadth controlled by the depth config (top-N by configurable
  ranking, not hard-coded symbols).
- **Health/audit**: `health` and `system_events` tables populated live, plus the
  written 72-hour audit report (per `THESIS.md` §8) covering symbol coverage, event
  counts, timestamp/sequence gaps, duplicate counts, resync counts, reconnect counts,
  REST failures, stale-stream detection, DB write failures, storage growth.
- **Storage foundation**: internal queue, single DB writer, SQLite WAL — built here
  once, reused unchanged by later product phases.
- **Capability registry**: initial registry entries for Spot's data classes, structured
  so Phase 2+ add entries rather than new code paths.

## Out of scope for this requirement

- USDⓈ-M, COIN-M, Options connectors (Phases 2–4).
- Anything in `docs/SCOPE.md`'s 🔴 list.
- Any analysis, aggregation-for-research, or query tooling beyond what's needed to
  write the 72-hour audit report itself.

## Acceptance criteria

- [ ] All data classes listed above are being collected and written to SQLite.
- [ ] Depth resync triggers correctly on a detected gap (verified, not just coded).
- [ ] All price/quantity columns are text/exact-decimal, never float.
- [ ] `raw_events` carries every ingested payload regardless of whether a normalized
      table also exists for it.
- [ ] The collector survives a forced WebSocket disconnect and resumes cleanly.
- [ ] A 72-hour continuous run completes and the audit report is written, with no
      unexplained gaps.
- [ ] `docs/ARCHITECTURE.md` §6 (tech stack) and §7 (repo layout) are updated to reflect
      what was actually built.
