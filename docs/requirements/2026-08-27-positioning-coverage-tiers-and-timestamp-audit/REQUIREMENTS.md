# Requirement: Positioning Data, Coverage Tiers, Timestamp Audit

**Opened:** 2026-08-27
**Status:** Implemented and unit-tested against the local mock; live verification of
the new REST endpoints still required (same sandbox constraint as everything else).

## Why

Pre-3-day-capture review from the user identified six things to check before locking
the collector. Verification results and what this requirement adds:

| # | Item | Finding |
|---|---|---|
| 1 | Liquidations | ✅ Already implemented (`!forceOrder@arr` → `liquidations` table, USDS-M + COIN-M). No new work. |
| 2 | Futures public positioning (long/short ratios) | ❌ Not implemented. **This requirement adds it.** |
| 3 | Options collector | ⚠️ Unchanged: raw-fidelity-only, disabled by default, blocked on live wire-format verification (this sandbox cannot reach Binance -- see `STATUS.md`). Not addressed here; tracked separately. |
| 4 | Two-tier coverage (don't let top-N starve the rest of the universe of research value) | ❌ Not tracked explicitly. **This requirement adds it.** |
| 5 | Preserve source (exchange) timestamp separately from receive timestamp everywhere | ⚠️ Partially true -- correct for trades/candles/depth_updates/liquidations, **missing for open_interest** (the actual bug the user's example called out), and inconsistently present elsewhere. **This requirement audits and fixes it.** |
| 6 | Keep raw payloads | ✅ Already true: `raw_events` is written for every envelope regardless of `kind`, independent of whether a normalized table exists. No new work. |

## What is needed

- **Futures positioning data**: poll Binance's public futures data endpoints
  (`globalLongShortAccountRatio`, `topLongShortAccountRatio`,
  `topLongShortPositionRatio`, `takerlongshortRatio`) for USDS-M (and COIN-M, where the
  same relative paths are expected to exist -- flagged for live re-verification) and
  store them minimally as requested: timestamp, symbol, metric, value, source, raw
  payload -- no interpretation.
- **Coverage tier tracking**: an explicit, queryable record of which tier
  (`BROAD` vs `HIGH_RESOLUTION`) each symbol had at each point in time, written
  every depth-refresh cycle, so "the model didn't find anything in small-caps" can
  never be quietly explained by "small-caps never got rich data" without that being
  visible in the data itself.
- **Timestamp audit**: every table that receives a Binance-supplied timestamp for its
  data point captures it in a dedicated column, distinct from `observed_at` (this
  collector's own receive/poll time). Where Binance's payload genuinely provides no
  timestamp (bookTicker), document that explicitly rather than leaving it looking like
  an oversight.

## Out of scope for this requirement

- Options (tracked in `2026-08-27-futures-and-options-collectors`).
- Any interpretation of positioning/OI/liquidation data (ratios, scores, signals) --
  per `docs/SCOPE.md`, this stays a pure ingredients collector.
- A live run against real Binance (blocked in this sandbox).

## Acceptance criteria

- [x] `futures_positioning` table exists and is populated for USDM (COIN-M attempted
      with the same relative paths; a wrong path fails loud as `rest_failure`, not
      silently, per the raw-preservation safety net).
- [x] `symbol_coverage` table exists, written every depth-refresh cycle, one row per
      universe symbol per cycle, tagging it `BROAD` or `HIGH_RESOLUTION`.
- [x] `open_interest` gains `observation_time` from Binance's own `time` field.
- [x] `mark_price`, `agg_trades`, `ticker_24h` gain `event_time` from Binance's `E`
      field, alongside their existing `observed_at`.
- [x] `depth_snapshots` gains optional `event_time`/`transaction_time` (present for
      futures REST snapshots, null for spot, which doesn't provide them).
- [x] `book_ticker`'s lack of a source timestamp is documented as an upstream Binance
      limitation, not silently left unexplained.
- [x] Existing tests updated for the new columns; new tests for positioning parsing/
      storage and coverage-tier writing.
