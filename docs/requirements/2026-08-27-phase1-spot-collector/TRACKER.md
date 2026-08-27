# Tracker: Phase 1 — Spot Collector

- [x] 1. Open decisions locked in `DESIGN.md` (aiohttp for REST+WS, aiosqlite/WAL,
      pyyaml registry, kline intervals 1m/5m/1h)
- [x] 2. `src/`, `config/`, `tests/` scaffolded
- [x] 3. `src/schema.py` DDL implemented (all products' tables, decimal-as-text)
- [x] 4. `src/storage.py` (queue consumer + single writer) implemented
- [x] 5. `src/config.py` registry loader + `config/settings.yaml` entries implemented
- [x] 6. Instrument metadata poller implemented (incl. `isMarginTradingAllowed`)
- [x] 7. Trade/aggTrade/bookTicker/ticker/candle handling implemented
- [x] 8. Depth snapshot+sync+resync state machine implemented (`src/depth_sync.py`,
      `DepthConnectionGroup` with true SUBSCRIBE/UNSUBSCRIBE)
- [x] 9. WebSocket reconnect/backoff implemented (`ws_messages` in `binance_client.py`)
- [x] 10. Health counters + rollup + system_events implemented (`src/health.py`)
- [x] 11. Tests written and passing (35 tests: depth resync incl. a real bug caught by
      the replay test, envelope/decimal-as-text, reconnect, REST 429/418 backoff,
      full pipeline integration test against a local mock Binance server)
- [ ] 12. **72-hour clean run against real Binance -- NOT DONE.** This sandbox's egress
      proxy blocks Binance (`api.binance.com`/`stream.binance.com` return 403) and does
      not support WebSocket upgrades at all (confirmed via the proxy's own status/README).
      All correctness testing here used a protocol-faithful local mock
      (`tests/mock_binance.py`), not the real exchange. Running the collector against
      live Binance from an environment with real network access, and writing the
      resulting audit report, is the one remaining acceptance criterion.
- [x] 13. `docs/ARCHITECTURE.md` updated to match the actual implementation
- [ ] 14. `docs/requirements/README.md` index -- update once item 12 (live run) lands;
      left as "in progress" until then, not "Done"
- [x] 15. This tracker kept current throughout

**Status:** Implemented and unit/integration-tested against a local mock; **live
verification against real Binance still required** (see item 12) before this
requirement can be marked Done.

## Scope note

The user asked to implement Spot, USDS-M Futures, COIN-M Futures, and Options together
rather than gating each on the prior product's 24h clean run (docs/THESIS.md #9's
staged rollout). All four share this requirement's framework (`src/storage.py`,
`src/ratelimit.py`, `src/binance_client.py`, `src/depth_sync.py`,
`src/connectors/market.py`) and were built in the same pass -- see
`docs/requirements/2026-08-27-futures-and-options-collectors/` for their own
requirement record. `config/settings.yaml` still lets each product be enabled
independently, so the original risk-isolation intent (don't run something new against
an already-stable collector) is preserved operationally even though the code landed
together.
