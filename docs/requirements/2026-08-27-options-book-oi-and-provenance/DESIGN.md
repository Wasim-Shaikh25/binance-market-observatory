# Design

## Options depth

- In `options.rest_market_loop`, poll `/eapi/v1/depth?symbol=&limit=100` per
  configured symbol.
- Parse to existing `depth_snapshot` envelope shape (`last_update_id`, `bids`,
  `asks`, `transaction_time` from Options `T`).
- No Options depth WS sync/resync (REST snapshot trail is the durable record).

## Options open interest

- Derive `(underlyingAsset, expiration)` pairs from configured symbols
  (`BTC-260828-65000-C` → `BTC` + `260828`).
- Poll `/eapi/v1/openInterest?underlyingAsset=&expiration=`.
- For each row, if symbol is in the configured universe (or universe is `all`),
  emit `kind=open_interest` with `open_interest=sumOpenInterest` (TEXT) and
  `observation_time` from Binance `timestamp`. Full row stays in `raw_events`.

## Provenance

- Add `raw_events.source_type TEXT NOT NULL` with values
  `websocket` | `rest_poll` | `rest_backfill`.
- `Envelope.source_type` optional; writer infers from `source_endpoint`
  (`wss:` → websocket, `http` → rest_poll) unless explicitly set.
- Schema migration via `ALTER TABLE` for existing DBs.
- Validator: provenance check PASSes when column exists and both websocket and
  rest_poll appear (or only rest_poll for Options-only runs).

## Inventory / matrix

- `OPTIONS/book` and `OPTIONS/open_interest` → `implemented=True`
- `EXCHANGE/rest_backfill_provenance` → `implemented=True` (column present;
  backfill crawler still absent — notes say so)
