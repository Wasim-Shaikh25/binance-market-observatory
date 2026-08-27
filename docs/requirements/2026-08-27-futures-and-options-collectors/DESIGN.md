# Design: USDⓈ-M / COIN-M Futures + Options Collectors

## Approach

Spot, USDS-M, and COIN-M share the same combined-stream WebSocket shape and REST
endpoint layout, differing only in base URLs, a couple of REST paths, and a small set
of futures-only extras. Rather than three near-duplicate connector modules, the shared
logic lives in `src/connectors/market.py` (`run_market_product`, `ConnectorContext`,
`ProductPaths`, `DepthConnectionGroup`, `select_depth_symbols`, etc.), and
`spot.py`/`usdm.py`/`coinm.py` are thin modules that just supply a `ProductPaths` value:

```python
USDM_PATHS = ProductPaths(
    exchange_info_path="/fapi/v1/exchangeInfo",
    depth_path="/fapi/v1/depth",
    is_futures=True,
    open_interest_path="/fapi/v1/openInterest",
    force_order_stream="!forceOrder@arr",
    mark_price_suffix="@markPrice@1s",
)
```

`is_futures=True` switches `DepthSyncTracker` to the `pu` (previous-final-update-ID)
continuity check instead of spot's `U == prev_u + 1` check, matching Binance's
documented futures depth-diff format (see `src/depth_sync.py`'s docstring).

Funding rate is derived from the `markPriceUpdate` stream (`r`/`T` fields) rather than
separately polling the funding-rate REST endpoint -- one fewer REST call competing for
weight budget, using data already being received.

Open interest has no WebSocket stream (Binance only exposes it via REST), so
`open_interest_loop` polls it per-symbol for whichever symbols are currently in the
depth-tracked set (`DepthConnectionGroup.target`), keeping REST weight usage bounded
by the same top-N config that already limits full-depth tracking, rather than polling
every symbol in the universe.

Liquidations (`!forceOrder@arr`) are a single all-symbols array stream, added directly
to the broad-stream connection group's stream list rather than per-symbol.

## Options

Options' public WS/REST payload shapes could not be verified against Binance's live
docs from this sandbox. `src/connectors/options.py` therefore only guarantees raw
fidelity: it polls `/eapi/v1/exchangeInfo` for instrument identity and subscribes to
`@trade`/`@ticker`/`@kline_*` streams per symbol, but routes every message to a `kind`
that has no entry in `storage.py`'s `_NORMALIZERS` map (e.g. `options_trade`), so it is
preserved in `raw_events` and nothing else -- deliberately, rather than writing
normalizers against guessed field names. `config/settings.yaml` ships Options
`enabled: false`. Before enabling it for real: confirm the current endpoint hosts,
stream naming, and payload field names against Binance's live Options API docs, then
add normalizers following the pattern in `connectors/common.py`.

## Non-goals

- No normalized Options tables yet (see above).
- No change to Phase 1's storage schema, rate limiting, or reconnect/depth-sync
  machinery -- this requirement is additive (new `ProductPaths` values, futures-only
  parsers in `connectors/common.py`) rather than modifying shared code's contracts.
