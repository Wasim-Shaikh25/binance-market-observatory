# Changelog

All notable changes to this project are recorded here. Read this file first, before
making any change — see `AGENTS.md` rule 5.

Format: reverse chronological, one entry per change, dated.

## 2026-08-27 (17)

- Enabled previously skipped config feeds:
  - Smoke: full kline set `1m, 5m, 15m, 1h, 4h, 1d` for Spot / USDS-M / COIN-M / Options
  - Production `settings.yaml`: Options **enabled** with a small symbol list + same
    kline set (not full-universe Options REST — rate-limit safe)
- Requirement: `docs/requirements/2026-08-27-enable-disabled-config-feeds/`

## 2026-08-27 (16)

- Fixed false 🟡 PARTIAL on **depth↔bookTicker** reconciliation: the check used
  the latest `depth_snapshots` row, often Options REST depth (no `book_ticker`).
  It now only pairs Spot/USDS-M/COIN-M snapshots with bookTicker.
- Requirement: `docs/requirements/2026-08-27-fix-depth-book-reconcile/`.

## 2026-08-27 (15)

- **ClickHouse is the durable hot store**; SQLite is optional/ephemeral:
  - `ClickHouseSink` now mirrors **all** normalizer kinds (not only trades/agg/book)
  - `database.persist: false` deletes the SQLite file after graceful stop when CH
    and/or the zstd archive is enabled
  - Smoke config: CH + archive on, `persist: false`; `--duration-seconds` for timed runs
- Live smoke `smoke_chprim_*` (~3 min): validation checklist **PASS** on products /
  intended feeds (Options WS still PARTIAL / announcements NOT_PUBLICLY_AVAILABLE)
- Size: SQLite ~95 MiB → ClickHouse **~8.1 MiB** (~12×); archive ~2.8 MiB; local
  `data/*.db` cleaned up after the checklist run
- Requirement:
  `docs/requirements/2026-08-27-clickhouse-primary-drop-sqlite/`
- 73 tests passing

## 2026-08-27 (14)

- **Dual-write sinks** (SQLite kept for comparison):
  - Streaming **NDJSON + zstd** raw archive (`src/raw_archive.py`)
  - Live **ClickHouse** sink (`src/clickhouse_sink.py`) for `raw_events` +
    trades/agg_trades/book_ticker
  - Config under `sinks:` in `settings.yaml` / enabled in `smoke_settings.yaml`
  - `zstandard` added to `requirements.txt`
- Smoke dual run: SQLite ~190 MB vs archive ~5 MB; CH counts track SQLite
  (graceful stop recommended so last batch flushes). Compare helper:
  `validation/script/compare_sqlite_clickhouse.py`
- Requirement folder:
  `docs/requirements/2026-08-27-dual-write-clickhouse-zstd-archive/`.
- 71 tests passing.

## 2026-08-27 (13)

- Installed ClickHouse via Docker (`bmo-clickhouse`, user `default` / password `bench`)
  and benchmarked the same smoke DB:
  SQLite ~107.7 MiB → ClickHouse active parts **~9.5 MiB** (~**11.3×** smaller)
  while keeping prices as String and `payload_json` readable.
- Script: `research/script/benchmark_clickhouse_load.py`
- Report: `research/report/clickhouse_benchmark_*/REPORT.md`
- Live collector still SQLite; no migration yet.
- Requirement folder:
  `docs/requirements/2026-08-27-clickhouse-readable-benchmark/`.

## 2026-08-27 (12)

- One-file storage format benchmark (no collector migration):
  `research/script/benchmark_storage_formats.py` on
  `data/market_smoke_complete_*.db` (~5 min / 167k raw_events).
  Results: SQLite ~108 MiB; raw NDJSON+gzip ~2.9 MiB; Parquet+ZSTD normalized
  ~3.4 MiB; Parquet raw_events ~3.4 MiB; ClickHouse N/A (not installed).
  Report: `research/report/storage_benchmark_*/REPORT.md`.
- Requirement folder:
  `docs/requirements/2026-08-27-storage-format-benchmark/`.

## 2026-08-27 (11)

- **Accepted limitations** recorded in `THESIS.md` §11 and `SCOPE.md`: no announcements
  scraper; Options WS is environment-dependent and must not block the project when
  REST covers the data.
- **`coverage_history`**: DEPTH tier intervals with `started_at` / `ended_at` /
  `reason` / `close_reason` (`entered_top_n`, `left_top_n`, `initial_assignment`, …).
- **Historical gap-fill crawler** (`src/gap_fill.py`): detects agg_trade ID holes and
  candle open_time holes; fetches public `/aggTrades` + `/klines`; writes with
  `source_type=rest_backfill`; never overwrites live UNIQUE rows; logs
  `gap_fill_jobs` + `gap_detected` / `gap_recovered` system events. Wired from
  `main` for Spot/USDM/COIN-M.
- Live checks: coverage_history populated with reasons; synthetic agg_trade hole
  recovered via REST backfill. **No 72h run in this change** — ready for operator
  continuous run next.
- Requirement folder:
  `docs/requirements/2026-08-27-gap-fill-and-coverage-history/`.
- 68 tests passing.

## 2026-08-27 (10)

- Implemented remaining checklist NOT_IMPLEMENTED items that are publicly available:
  - **Options book**: REST `/eapi/v1/depth` → `depth_snapshots` (poll trail; no WS sync).
  - **Options open interest**: REST `/eapi/v1/openInterest` → `open_interest`
    (`product=OPTIONS`, `sumOpenInterest` as TEXT).
  - **Provenance**: `raw_events.source_type` = `websocket` | `rest_poll` |
    `rest_backfill` (inferred from endpoint; explicit override supported). Historical
    gap-fill crawler not built — column + contract only.
- Smoke: `config/smoke_options_settings.yaml` →
  `data/market_smoke_opt_*.db` (depth=8, OI=6, source_type=rest_poll, 0 failures).
- Inventory/validator updated; 63 tests passing.
- Requirement folder:
  `docs/requirements/2026-08-27-options-book-oi-and-provenance/`.

## 2026-08-27 (9)

- **Closed remaining validation gaps** (except wall-clock 72h):
  - Multi-product live smoke (Spot + USDM + COIN-M + Options) with USDM host fix
    and `depth.top_n: 1` → both **BROAD** and **HIGH_RESOLUTION** tiers.
  - Options: REST instruments/trades/ticker/mark(IV+greeks)/index →
    `trades` / `ticker_24h` / `options_mark` / `options_index`; WS best-effort
    on `fstream.binancefuture.com/eoptions` (0 frames here — PARTIAL, not FAIL).
  - Exchange system status: `/sapi/v1/system/status` → `exchange_status`.
  - Validator: disabled products → NOT_IMPLEMENTED; Options + exchange_status checks;
    inventory marks implemented REST Options + system_status.
  - Report: `validation/report/BINANCE_DATA_CAPTURE_REPORT.md` from
    `data/market_smoke_complete_20260827T174743Z.db` — products PASS; Options
    summary PASS with WS PARTIAL; 0 rest/db failures.
- Production `settings.yaml` already includes 15m/4h/1d klines; Options remains
  disabled by default (enable when wanted).
- Requirement folder:
  `docs/requirements/2026-08-27-complete-remaining-validation-gaps/`.
- 61 tests passing.

## 2026-08-27 (8)

- **Fixed USDS-M missing broad streams**: root cause was the WebSocket host.
  `wss://fstream.binance.com` accepted the connection but delivered only
  trade+bookTicker; `wss://fstream.binancefuture.com` delivers the full set
  (aggTrade, ticker, kline, markPrice@1s, !forceOrder@arr). Updated
  `config/settings.yaml`, `config/smoke_settings.yaml`, and added
  `config/smoke_usdm_settings.yaml`. Live re-smoke: USDM matrix cells PASS.
- Also check more-specific stream suffixes first (`@aggTrade` before `@trade`).
- **AGENTS.md rule 8**: all non-runtime scripts/reports go under
  `research/{script,report}/` or `validation/{script,report}/`. Moved
  `BINANCE_DATA_CAPTURE_REPORT.md` and smoke audit into `validation/report/`;
  added `validation/script/run_validation.py` + USDM probes; validate/audit
  default `--out` paths updated.
- Requirement folder:
  `docs/requirements/2026-08-27-usdm-ws-host-and-report-layout/`.

## 2026-08-27 (7)

- Implemented the complete data-capture validation checklist as
  `python -m src.validate` → `BINANCE_DATA_CAPTURE_REPORT.md`.
  Statuses are mandatory: PASS / PARTIAL / FAIL / NOT_IMPLEMENTED /
  NOT_PUBLICLY_AVAILABLE / NO_DATA. Covers products, instruments, raw_events,
  trades/agg/book/depth/candles/ticker, futures mark/funding/OI/liquidations/
  positioning, coverage tiers, timestamps, system health, decimal TEXT check,
  raw↔normalized samples, trade↔candle and depth↔bookTicker reconciliations,
  storage growth, and the five research-readiness questions — no trading
  interpretation.
- Ran against `data/market_smoke_final_*.db`. Honest findings include:
  Spot/COIN-M largely PASS; **USDS-M PARTIAL/FAIL** because this run stored
  trades+bookTicker+depth+OI+positioning but **zero** aggTrade/ticker/kline/
  markPrice/forceOrder in `raw_events` (same code path works for Spot/COIN-M —
  needs a follow-up connector fix); Options NOT_IMPLEMENTED; smoke list-mode
  coverage tiers all HIGH_RESOLUTION (PARTIAL vs full-universe BROAD claim).
- Requirement folder:
  `docs/requirements/2026-08-27-complete-data-validation-checklist/`.
- 58 tests passing.

## 2026-08-27 (6)

- First live smoke against real Binance (this Windows host can reach the
  exchange; earlier sandbox notes about 403 do not apply here). Used
  `config/smoke_settings.yaml` (BTC/ETH only, 1-minute polls) for ~2 minutes.
  Confirmed Spot / USDS-M / COIN-M write into every intended table
  (`raw_events`, trades, depth, funding, OI, liquidations, mark price,
  positioning, coverage tiers, etc.). Options still disabled.
- Fixed three live-only bugs found during that run:
  - **COIN-M positioning** needs `pair=BTCUSD`, not `symbol=BTCUSD_PERP`
    (400). Added `positioning_query_param` + `coinm_pair_from_symbol`.
  - **COIN-M has no `takerlongshortRatio`** (404); use `takerBuySellVol` and
    store `takerBuyVol` / `takerSellVol` as separate metric rows.
  - **Depth resync storm**: USDM logged ~1000 `depth_resync` events/minute
    because diffs were applied (and failed) during REST snapshot fetch
    instead of being buffered. Buffer-while-resyncing + snapshot bridge
    retry; post-fix smoke shows single-digit resyncs and 0 REST/DB write
    failures.
- New requirement folder:
  `docs/requirements/2026-08-27-live-smoke-verification-fixes/`.
- 55 tests passing.

## 2026-08-27 (5)

- Addressed a pre-3-day-capture review: verified liquidations and raw-payload
  preservation were already correct (no change needed), and closed three real gaps:
  - **Futures positioning data**: new `futures_positioning` table + `positioning_loop`
    polling Binance's public long/short ratio endpoints
    (`globalLongShortAccountRatio`, `topLongShortAccountRatio`,
    `topLongShortPositionRatio`, `takerlongshortRatio`) for the depth-tracked symbol
    set on USDS-M/COIN-M. Stored exactly as requested -- timestamp, symbol, metric,
    value, source, raw payload -- with no interpretation. These endpoint paths are
    unverified against live Binance docs (this sandbox still can't reach it); a wrong
    path fails loud as `rest_failure`, not silently.
  - **Coverage tiers**: new `symbol_coverage` table, written every depth-refresh cycle
    for the *entire* symbol universe (not just the depth-tracked subset), tagging each
    symbol `BROAD` or `HIGH_RESOLUTION` -- so a future "nothing interesting in
    small-caps" finding can never be silently confounded with "small-caps never got
    instrumented."
  - **Timestamp audit**: added `open_interest.observation_time` (the actual bug the
    review's "collected at 13:05 != measured at 13:05" example called out -- it was
    previously missing entirely), plus `event_time` on `mark_price`/`agg_trades`/
    `ticker_24h` and `event_time`/`transaction_time` on `depth_snapshots`. Documented
    (didn't fabricate) that `book_ticker` has no source timestamp because Binance's
    payload for that stream doesn't provide one.
  - Options status unchanged: raw-fidelity-only, disabled by default, still blocked on
    live wire-format verification -- explicitly out of scope for this change.
  - New requirement folder:
    `docs/requirements/2026-08-27-positioning-coverage-tiers-and-timestamp-audit/`.
  - Caught another real bug via the same automated INSERT column/placeholder check
    used last time: `_write_depth_snapshot` was short one `?` placeholder after adding
    the two new columns -- fixed before it ever ran.
  - 11 new tests, 52 total, all passing.

## 2026-08-27 (4)

- Added per-run database files and background run scripts, per the user's request:
  - `config/settings.yaml`'s `database.path` now defaults to `data/market_{run_id}.db`;
    `src/config.py` gained `resolve_db_path`/`find_latest_db_path`, and `src/main.py`
    generates a run ID (UTC timestamp, overridable via the `RUN_ID` env var) and logs
    the resolved path at startup. A path with no `{run_id}` placeholder still works
    unchanged (fixed-file mode), so nothing existing broke.
  - `src/audit.py` gained `--db` and, without it, auto-discovers the most recently
    modified run so "audit the run I just did" doesn't require remembering a filename.
  - Added `scripts/collector.sh` (start/stop/status/tail) to run the collector detached
    via `nohup` + a PID file, with SIGTERM for graceful shutdown (reuses `main.py`'s
    existing signal handling) and one log file per run under `data/logs/`.
  - Verified live in this sandbox: two consecutive start/stop cycles produced two
    distinct database and log files, and `python -m src.audit` correctly picked the
    newer one. Actual data collection during that smoke test failed as expected --
    this sandbox still can't reach Binance -- unrelated to this change.
  - New requirement folder:
    `docs/requirements/2026-08-27-per-run-db-and-background-run-scripts/`.
  - 6 new tests (`tests/test_run_id.py`), 41 total, all passing.

## 2026-08-27 (3)

- Implemented the full collector: Spot, USDS-M Futures, COIN-M Futures (raw-fidelity
  Options, disabled by default). New: `src/config.py`, `src/models.py`, `src/schema.py`,
  `src/storage.py`, `src/ratelimit.py`, `src/binance_client.py`, `src/depth_sync.py`,
  `src/health.py`, `src/audit.py`, `src/main.py`, `src/connectors/*`,
  `config/settings.yaml`, 35 tests including a local protocol-faithful mock Binance
  server (`tests/mock_binance.py`) and a full pipeline integration test.
- **Environment constraint discovered and documented**: this sandbox's egress proxy
  blocks `api.binance.com`/`stream.binance.com` (403, org policy) and does not support
  WebSocket upgrades through it at all (confirmed via the proxy's own status/README).
  All testing here therefore validated the pipeline against a local mock reproducing
  Binance's real wire format, not against live Binance. A live run in an environment
  with real network access is still required before Phase 1 (or the futures/options
  work) can be marked Done -- tracked as the one open item in both requirement
  folders' `TRACKER.md`.
- Testing caught and fixed three real bugs before they could have caused silent data
  loss in production: two SQL column/placeholder-count mismatches in `book_ticker` and
  `ticker_24h` inserts (would have crashed every write for those streams), a
  depth-resync replay bug where the first buffered event after a snapshot skipped its
  intended continuity-check exemption, and a reconnect-detection dead branch in
  `ws_messages` (aiohttp swallows CLOSE/CLOSING/CLOSED in its iterator, so the
  "disconnected" event was never actually emitted on a clean server-initiated close).
- Added `docs/requirements/2026-08-27-futures-and-options-collectors/` to record the
  futures/options work as its own requirement, per the user's explicit request to
  implement the full product scope in one pass rather than gating each product behind
  the prior one's 24h clean run (docs/THESIS.md #9's original staged rollout).
- Updated `docs/ARCHITECTURE.md` #6-#7 (tech stack, repo layout) to match what was
  actually built.

## 2026-08-27 (2)

- Added `AGENTS.md` rule 8: recommends the [Ponytail](https://github.com/DietrichGebert/ponytail)
  Claude Code plugin (enforces "check existing/stdlib/native before writing new code")
  for whoever implements the collector. It's a session-level plugin enabled via
  `/plugin marketplace add` + `/plugin install`, not a repo dependency — no code
  changed here.

## 2026-08-27

- Established the documentation/governance scaffold for the project:
  `docs/THESIS.md`, `docs/SCOPE.md`, `docs/ARCHITECTURE.md`, `AGENTS.md`, this file,
  and `STATUS.md`.
- Established the `docs/requirements/` spec-driven workflow
  (`docs/requirements/README.md`) and created its first two folders:
  - `2026-08-27-repo-scaffold-and-governance` (this change; Done).
  - `2026-08-27-phase1-spot-collector` (next unit of work; not started).
- Rewrote root `README.md` to link the above.
- No collector code exists yet — this change is documentation/process only.
