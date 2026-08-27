# Requirements: Fix USDS-M WS host + research/validation layout

**Opened:** 2026-08-27  
**Scope:** Collector correctness + repo layout for scripts/reports. No trading/ML.

## Why

1. Validation found USDS-M missing aggTrade/ticker/kline/markPrice/forceOrder while
   Spot/COIN-M received them. Live probe showed `wss://fstream.binance.com` accepts
   the socket but delivers only trade+bookTicker; `wss://fstream.binancefuture.com`
   delivers the full public stream set.
2. Scripts and generated reports were accumulating in the repo root / `data/`.
   Standardize on `research/` and `validation/` each with `script/` and `report/`.

## Acceptance

- USDM `ws_base_url` updated; smoke re-run shows those streams in raw_events.
- `AGENTS.md` rule for research/validation folders.
- Existing validation reports moved under `validation/report/`.
- Validate CLI default output path under `validation/report/`.
