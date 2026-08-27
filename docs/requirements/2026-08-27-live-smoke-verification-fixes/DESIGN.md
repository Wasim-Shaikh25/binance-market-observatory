# Design: Live Smoke Verification Fixes

## COIN-M positioning

- `ProductPaths.positioning_query_param`: `"symbol"` (USDM default) or `"pair"` (COIN-M).
- `common.coinm_pair_from_symbol`: `BTCUSD_PERP` / `BTCUSD_250926` → `BTCUSD`.
- `positioning_loop` dedupes by query key so multiple contracts on the same pair
  do not double-poll.
- COIN-M endpoints: `globalLongShortAccountRatio`, `topLongShortAccountRatio`,
  `topLongShortPositionRatio`, `takerBuySellVol` (not `takerlongshortRatio`).
- `common.positioning_rows`: splits `takerBuySellVol` into `takerBuyVol` +
  `takerSellVol` rows so `futures_positioning.value` stays NOT NULL without
  inventing a ratio.

## Depth resync

- While `symbol in _resyncing`, only `tracker.buffer(event)` — never
  `apply_update` against the old id.
- On `resync_needed`: log once, `reset()`, buffer the triggering event, fetch
  snapshot (retry up to 5× on bridge failure).
- `apply_snapshot` returns `bool`; on bridge failure restores the pending buffer
  and clears book state so a retry can succeed.

## Smoke config

- `config/smoke_settings.yaml`: small symbol list + 1-minute polls for local
  live verification only (not production defaults).
