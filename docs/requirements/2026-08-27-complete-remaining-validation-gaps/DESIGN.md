# Design

## System status

- New table `exchange_status` (status_code, msg, observed_at, payload_json)
- Poller in `src/connectors/system_status.py`, started from `main.py` when Spot
  REST is available (or always against api.binance.com)
- Kind `exchange_status` → writer

## Options

- `ws_base_url`: `wss://fstream.binancefuture.com/eoptions` (nbstream 404 here;
  same host family as USDM fix)
- Stream symbols **not lowercased** (Binance Options docs use mixed-case symbols)
- REST loops (list-mode symbols): `/eapi/v1/trades`, `/ticker`, `/mark`, `/index`
- New tables: `options_mark`, `options_index` (IV/greeks in options_mark)
- Trades/ticker: map into existing `trades` / `ticker_24h` where fields fit;
  else raw-only + dedicated tables
- Instruments: enrich snapshot with strike, expiry, side C/P in payload + columns

## Validator

- If product disabled → NOT_IMPLEMENTED for that product's feed checks
- Inventory: Options implemented=True for instruments/mark/index/ticker/trades REST

## Smoke

- Spot/USDM/COINM + Options enabled; depth top_n=1 with 2 symbols → BROAD+HIGH_RESOLUTION
- Options symbol_list: 2 near-term BTC options
