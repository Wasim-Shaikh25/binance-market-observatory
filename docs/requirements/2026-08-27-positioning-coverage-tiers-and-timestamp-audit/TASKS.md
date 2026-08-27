# Tasks: Positioning Data, Coverage Tiers, Timestamp Audit

1. Verify liquidations and raw-payload preservation are already implemented (they are
   -- no new work).
2. Schema: add `futures_positioning`, `symbol_coverage` tables; add `observation_time`
   to `open_interest`; add `event_time` to `mark_price`/`agg_trades`/`ticker_24h`; add
   `event_time`/`transaction_time` to `depth_snapshots`; document `book_ticker`'s lack
   of a source timestamp as an upstream limitation.
3. Parsers: `parse_open_interest`, `parse_positioning_entry` (+ `POSITIONING_VALUE_FIELDS`
   metric-to-field map); add `event_time` extraction to `parse_agg_trade`,
   `parse_ticker_24h`, `parse_mark_price`, `parse_depth_snapshot`.
4. Storage writers: update `_write_agg_trade`, `_write_ticker_24h`,
   `_write_depth_snapshot`, `_write_open_interest`, `_write_mark_price` for the new
   columns; add `_write_futures_positioning`, `_write_symbol_coverage`.
5. `ProductPaths` gains `positioning_endpoints` + `positioning_path_prefix`;
   `usdm.py`/`coinm.py` populate them (flagged as unverified against live docs).
6. Implement `positioning_loop` (polls the depth-tracked symbol set, same REST-weight
   rationale as `open_interest_loop`) and wire it into `run_market_product`.
7. Implement `_record_coverage_tiers` and call it from `depth_supervisor` every
   depth-refresh cycle, for the whole universe (not just the high-resolution subset).
8. Add `positioning_poll_minutes` to `config.py`'s `ProductConfig` and
   `config/settings.yaml`.
9. Update `src/health.py`'s audit report with "Coverage tiers" and "Futures
   positioning" sections.
10. Tests: new parser tests, new storage tests, extend the existing Spot integration
    test with a coverage-tier assertion (already exercises `depth_supervisor`).
11. Update `docs/ARCHITECTURE.md` (§3.1 table list, new §5.5) and this folder's docs.
12. Update `CHANGELOG.md`, `STATUS.md`, `docs/requirements/README.md`.
