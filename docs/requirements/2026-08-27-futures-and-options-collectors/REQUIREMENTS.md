# Requirement: USDⓈ-M / COIN-M Futures + Options Collectors

**Opened:** 2026-08-27
**Status:** Implemented and unit/integration-tested against a local mock; live
verification against real Binance still required.

## Why

The user explicitly asked to implement the full product scope (Spot, USDS-M Futures,
COIN-M Futures, Options) in one pass rather than gating each product behind the prior
one's 24h clean run, as `docs/THESIS.md` #9 originally specified. This requirement
records that deliberate deviation and what was built as a result, without retroactively
rewriting `2026-08-27-phase1-spot-collector`'s own record (per the requirements
workflow's rule against widening an old folder's scope after the fact).

## What is needed

- **USDS-M Futures** (`src/connectors/usdm.py`): trade, aggTrade, bookTicker, ticker,
  klines, depth (snapshot+sync+resync), funding rate (derived from the markPrice
  stream), open interest (REST-polled for depth-tracked symbols), liquidations
  (`!forceOrder@arr`), instrument metadata.
- **COIN-M Futures** (`src/connectors/coinm.py`): identical data classes to USDS-M,
  against `dapi.binance.com`/`dstream.binance.com`.
- **Options** (`src/connectors/options.py`): raw-fidelity-only connector -- see its
  docstring. This sandbox cannot reach Binance to verify the current Options wire
  format, so normalized tables are deliberately not implemented for it yet; every
  message is still preserved in `raw_events`. Disabled by default in
  `config/settings.yaml`.
- Both futures connectors reuse Phase 1's framework unchanged: `src/storage.py`,
  `src/ratelimit.py`, `src/binance_client.py`, `src/depth_sync.py`, and the generic
  `src/connectors/market.py` (parameterized by `ProductPaths` per product).

## Out of scope for this requirement

- Anything on `docs/SCOPE.md`'s 🔴 list.
- Normalized Options tables (blocked on live wire-format verification).
- A live run against real Binance (this sandbox cannot reach it -- see `STATUS.md`).

## Acceptance criteria

- [x] USDS-M and COIN-M connectors implemented, sharing Phase 1's framework rather than
      duplicating it.
- [x] Futures-specific data classes (funding rate, open interest, liquidations, mark
      price) implemented and unit-tested (`tests/test_common_parsers.py`,
      `tests/test_storage.py`).
- [x] Options connector implemented with raw-fidelity-only storage and a clear
      docstring explaining why, disabled by default.
- [x] `config/settings.yaml` lets every product be enabled/disabled independently, so
      the original risk-isolation intent (don't run something new against an
      already-stable collector) stays available operationally.
- [ ] Live run against real Binance for USDS-M/COIN-M, and live wire-format
      verification for Options -- both blocked in this sandbox, required before
      production use.
