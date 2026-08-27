# Tasks: USDⓈ-M / COIN-M Futures + Options Collectors

1. Add futures-only payload parsers to `src/connectors/common.py`: `parse_mark_price`,
   `funding_from_mark_price`, `parse_force_order`.
2. Extend `src/connectors/market.py`'s `ProductPaths` with futures-only fields
   (`is_futures`, `open_interest_path`, `force_order_stream`, `mark_price_suffix`) and
   route their messages in `handle_broad_message`.
3. Implement `open_interest_loop`, polling only the depth-tracked symbol set.
4. Implement `src/connectors/usdm.py` and `src/connectors/coinm.py` as thin
   `ProductPaths` + `run_market_product` wrappers.
5. Add futures-only DB writers to `src/storage.py`: `_write_funding_rate`,
   `_write_open_interest`, `_write_liquidation`, `_write_mark_price`.
6. Add `usdm_futures`/`coinm_futures`/`options` entries to `config/settings.yaml`.
7. Implement `src/connectors/options.py` as a raw-fidelity-only connector; document why
   in its docstring; ship `enabled: false` by default.
8. Unit-test the new parsers and DB writers (`tests/test_common_parsers.py`,
   `tests/test_storage.py` -- liquidation/funding rows, cross-product identifiability).
9. Update `docs/ARCHITECTURE.md` and this folder's own docs to reflect what was built.
10. Keep this folder's `TRACKER.md` current.
