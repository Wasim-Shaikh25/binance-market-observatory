# Design: Positioning Data, Coverage Tiers, Timestamp Audit

## Positioning data

New table `futures_positioning`: `id, exchange, product, symbol, metric, value,
observation_time, source_endpoint, observed_at, payload_json`. `metric` is the
endpoint name (`globalLongShortAccountRatio`, `topLongShortAccountRatio`,
`topLongShortPositionRatio`, `takerlongshortRatio`); `value` is that endpoint's primary
ratio field as text, unmodified -- no derived scores. `observation_time` is Binance's
own `timestamp` field from the response; `observed_at` is when this collector polled it.

`ProductPaths` gains `positioning_endpoints: list[str]`, populated for USDM and COIN-M
with the four metrics above under `/futures/data/<metric>`. A new
`positioning_loop(cfg, ctx, paths, symbols_provider)` polls each endpoint per
depth-tracked symbol (same rationale as `open_interest_loop`: bound REST weight usage
by the same top-N config already limiting full-depth tracking) on a configurable
`positioning_poll_minutes` interval. These specific endpoint paths could not be
verified against live Binance docs from this sandbox (see STATUS.md's standing
constraint) -- a wrong path surfaces as a `rest_failure` system_event, which is the
correct, visible failure mode rather than silently storing nothing or storing garbage.

## Coverage tiers

New table `symbol_coverage`: `id, product, symbol, tier, observed_at`, `tier` one of
`BROAD` / `HIGH_RESOLUTION`. Written from `depth_supervisor` (`connectors/market.py`)
at the same cadence as the existing depth-refresh cycle (`depth.refresh_minutes`):
after computing the universe and the selected depth-tracked set, one row per universe
symbol is queued, tagged by whether it's in the depth set that cycle. This makes tier
assignment a first-class, queryable fact ("what tier did symbol X have at time T"),
not something to infer indirectly from which other tables happen to have rows for it.

## Timestamp audit

Went table-by-table through everything that receives a Binance-supplied timestamp:

| Table | Source timestamp column | Status |
|---|---|---|
| trades, agg_trades | `trade_time` (+ `event_time` added to agg_trades) | trades already had both; agg_trades gains `event_time` |
| book_ticker | none | **documented as an upstream limitation** -- Binance's bookTicker payload carries no timestamp field at all, only an update ID; fabricating one would be worse than admitting the gap |
| ticker_24h | `open_time`/`close_time` (+ `event_time` added) | window bounds already present; `event_time` (the push time) added for consistency |
| candles | `open_time`/`close_time` | already correct, no change |
| depth_updates | `event_time` | already correct, no change |
| depth_snapshots | none | **gains optional `event_time`/`transaction_time`** -- present on futures' REST depth snapshot response, absent on spot's (which genuinely doesn't return them); both nullable |
| funding_rate | `funding_time` | already correct (Binance's own next-funding-time) |
| open_interest | none | **gains `observation_time`** from Binance's own `time` field -- this was the exact bug the user's "collected at 13:05 != measured at 13:05" example called out |
| liquidations | `event_time` | already correct, no change |
| mark_price | `next_funding_time` (+ `event_time` added) | gains `event_time` (the push time) for consistency |
| futures_positioning | `observation_time` (new table) | built correct from the start |

`observed_at` (this collector's receive/poll time) stays on every table unchanged --
the fix is adding the missing *source* timestamp alongside it, never replacing one
with the other.

## Non-goals

- No interpretation of any new data (positioning ratios stay raw values, coverage
  tiers are a factual record, not a quality judgment).
- No change to existing correct timestamp handling (trades, candles, depth_updates,
  liquidations, funding_rate were already right).
