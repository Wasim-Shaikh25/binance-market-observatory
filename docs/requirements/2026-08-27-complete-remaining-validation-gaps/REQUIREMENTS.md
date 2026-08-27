# Requirements: Complete remaining validation gaps

**Opened:** 2026-08-27  
**Scope:** Close open validation checklist items that are completable without a
literal 72-hour wall-clock wait. No trading/ML.

## In scope

1. Multi-product live smoke (Spot + USDM + COIN-M + Options) with fixed USDM host
2. Validator: disabled products → NOT_IMPLEMENTED (not FAIL)
3. BROAD coverage tier visible (top_n < universe in smoke)
4. Exchange system status poller (public `/sapi/v1/system/status`)
5. Options: live-verified instruments + REST mark/index/ticker/trades storage;
   WS base URL corrected; uppercase stream symbols
6. Production kline intervals include 15m/4h/1d where configured
7. Full validation report under `validation/report/`

## Out of scope / honest limits

- A real 72-hour continuous clean run (time-gated; start instructions only)
- Authenticated endpoints
- Fabricating Options WS data if this network still cannot receive Options WS frames
