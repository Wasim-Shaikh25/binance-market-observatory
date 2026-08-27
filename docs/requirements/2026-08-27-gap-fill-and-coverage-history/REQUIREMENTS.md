# Requirements: Gap-fill crawler + coverage_history + accepted limits

**Opened:** 2026-08-27  
**Why:** Close the last implementable collector gaps before the operational
72h run. Record explicit non-goals so they are not chased again.

## In scope

1. Document accepted limitations in `THESIS.md` / `SCOPE.md`:
   - No stable public announcements feed → not a failure
   - Options WS environment-dependent; REST is authoritative where it covers the data
2. `coverage_history` table with started_at / ended_at / reason for DEPTH tier changes
3. Historical gap-fill crawler for public REST-recoverable feeds:
   - `agg_trades` via ID gaps → `/aggTrades` with `source_type=rest_backfill`
   - `candles` via open_time gaps → `/klines` with `source_type=rest_backfill`
   - Never overwrite live rows (UNIQUE + INSERT OR IGNORE / REPLACE only for candles
     when backfill is final and no live conflict policy: prefer keep existing)
4. Validator updates for coverage_history + gap_fill activity
5. Stop before any 72h run — validate with tests (+ optional short smoke of crawler)

## Out of scope

- Scraping announcements
- Blocking on Options WS
- Individual `/historicalTrades` (API-key) backfill
- 72-hour continuous run (operator step after this lands)
- Any SCOPE.md 🔴 item
