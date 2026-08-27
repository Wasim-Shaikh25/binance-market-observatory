# Tracker: Live Smoke Verification Fixes

- [x] 1. COIN-M `pair=` + `coinm_pair_from_symbol`
- [x] 2. COIN-M `takerBuySellVol` → `takerBuyVol`/`takerSellVol` rows
- [x] 3. Depth buffer-during-resync + snapshot bridge retry
- [x] 4. Unit tests
- [x] 5. Live smoke against Binance (`config/smoke_settings.yaml`) — all intended
      tables populated; 0 REST/DB write failures; depth_resync single-digit
- [x] 6. CHANGELOG / STATUS / index updated

**Status:** Done. Production defaults in `config/settings.yaml` unchanged;
use `smoke_settings.yaml` only for short verification runs.
