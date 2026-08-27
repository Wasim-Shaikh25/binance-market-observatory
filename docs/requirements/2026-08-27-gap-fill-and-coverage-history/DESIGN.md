# Design

## Accepted limitations (docs)

Add THESIS §11 (or amend §3/§8) with the user's exact policy wording. SCOPE:
mark announcements as accepted absence; Options WS non-blocking; gap-fill and
coverage_history as in-scope.

## coverage_history

```sql
coverage_history (
  product, symbol, feed,   -- feed = 'DEPTH' for tier tracking
  tier,                    -- BROAD | HIGH_RESOLUTION
  started_at, ended_at,    -- ended_at NULL = currently open
  reason,                  -- entered_top_n | left_top_n | initial_assignment | ...
  close_reason             -- set when row is closed
)
```

On each depth-refresh coverage pass, compare desired tier vs open row; close +
open via queue envelopes so the single DB writer owns mutations.

## Gap-fill crawler

Module `src/gap_fill.py`, loop started from `main` per enabled Spot/USDM/COIN-M:

1. Detect agg_trade_id holes in a lookback window
2. Page `GET …/aggTrades?symbol=&fromId=` until hole filled or live frontier
3. Enqueue `kind=agg_trade`, `source_type=rest_backfill`
4. Detect candle `open_time` holes for configured intervals; page `/klines`
5. Enqueue `kind=candle`, `source_type=rest_backfill`, `is_final=True`
6. Record `gap_fill_jobs` + `system_events` (`gap_detected` / `gap_recovered`)

Dedup: existing UNIQUE on `(product,symbol,agg_trade_id)` and candle
`(product,symbol,interval,open_time)` — INSERT OR IGNORE / OR REPLACE must not
clobber a live websocket row's payload when the id already exists. Trades writer
already IGNORE; candles use REPLACE today — for backfill use IGNORE-equivalent
by checking or adding a backfill-safe insert path.

Paths: Spot `/api/v3/…`, USDM `/fapi/v1/…`, COIN-M `/dapi/v1/…`.
