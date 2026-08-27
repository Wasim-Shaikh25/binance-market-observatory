# Tracker: USDⓈ-M / COIN-M Futures + Options Collectors

- [x] 1. Futures-only parsers added to `connectors/common.py`
- [x] 2. `ProductPaths` extended; futures message routing added to `market.py`
- [x] 3. `open_interest_loop` implemented (polls depth-tracked symbols only)
- [x] 4. `connectors/usdm.py` and `connectors/coinm.py` implemented
- [x] 5. Futures DB writers added to `storage.py`
- [x] 6. `config/settings.yaml` entries added for all three products
- [x] 7. `connectors/options.py` implemented (raw-fidelity-only, disabled by default)
- [x] 8. Unit tests written and passing
- [x] 9. `docs/ARCHITECTURE.md` updated
- [x] 10. This tracker kept current

**Status:** Implemented and tested against the local mock; a live run against real
Binance for USDS-M/COIN-M and live wire-format verification for Options are still
required before production use (blocked in this sandbox -- see `STATUS.md`).
