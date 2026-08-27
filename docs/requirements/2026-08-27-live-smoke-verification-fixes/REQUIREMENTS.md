# Requirements: Live Smoke Verification Fixes

**Opened:** 2026-08-27  
**Why:** First live run against real Binance (this machine can reach the exchange)
surfaced three wire-format / correctness bugs that the mock suite could not catch.
Fix them so a multi-day capture stores the intended positioning data and does not
thrash depth resyncs.

## In scope

- COIN-M positioning query param must be `pair=` (not `symbol=`).
- COIN-M has no `takerlongshortRatio` endpoint; use `takerBuySellVol` and store
  buy/sell volumes as separate metric rows (value NOT NULL).
- Depth resync storm: buffer diffs while a REST snapshot is in flight; do not
  re-apply against a stale book id every 100ms.

## Out of scope

- Options enablement / normalizers
- Full-universe multi-day capture (separate operational step)
- Changing Spot/USDM positioning endpoints (verified working as-is)

## Acceptance

- Short live smoke (limited symbols) writes all intended normalized tables with
  zero `rest_failure` / `db_write_failure` for positioning.
- USDM/COIN-M `depth_resync` counts are small (startup/rare gaps), not hundreds
  per minute per symbol.
- Tests covering `coinm_pair_from_symbol`, `positioning_rows`, and stale-snapshot
  buffer restore pass.
