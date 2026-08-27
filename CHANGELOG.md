# Changelog

All notable changes to this project are recorded here. Read this file first, before
making any change — see `AGENTS.md` rule 5.

Format: reverse chronological, one entry per change, dated.

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
