# Tracker: Positioning Data, Coverage Tiers, Timestamp Audit

- [x] 1. Liquidations / raw-payload preservation verified already implemented
- [x] 2. Schema changes (futures_positioning, symbol_coverage, timestamp columns)
- [x] 3. New/extended parsers in `connectors/common.py`
- [x] 4. Storage writers updated/added
- [x] 5. `ProductPaths` positioning fields; `usdm.py`/`coinm.py` populated
- [x] 6. `positioning_loop` implemented and wired in
- [x] 7. `_record_coverage_tiers` implemented and wired into `depth_supervisor`
- [x] 8. Config plumbing (`positioning_poll_minutes`)
- [x] 9. Audit report sections added
- [x] 10. Tests written and passing (52 total, up from 41)
- [x] 11. `docs/ARCHITECTURE.md` updated
- [x] 12. `CHANGELOG.md`, `STATUS.md`, requirements index updated

**Status:** Done for what's addable from this sandbox. One caveat carried forward
honestly: the `/futures/data/<metric>` positioning endpoint paths could not be
verified against Binance's live docs (no network access here) -- they're implemented
generically enough that a wrong path fails loud as a `rest_failure` system_event
rather than silently storing nothing, but confirm them before trusting the
`futures_positioning` table's contents on a live run.

Options remains out of scope for this requirement (tracked in
`2026-08-27-futures-and-options-collectors`) -- unchanged status: raw-fidelity-only,
disabled by default, blocked on live wire-format verification.
