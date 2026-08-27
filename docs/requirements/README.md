# Requirements Workflow

This folder is the spec-driven work log for the project. Every unit of work starts here
before any code is written. Full rules live in `AGENTS.md`; this file is the quick
how-to.

## Creating a new requirement

1. Make a new folder: `docs/requirements/<YYYY-MM-DD>-<short-kebab-slug>/`
   - `YYYY-MM-DD` = the date the requirement was opened.
   - `<short-kebab-slug>` = a few words describing what the requirement covers, e.g.
     `phase1-spot-collector`, `depth-resync-fix`, `options-connector`.
2. Inside it, create four files, in this order:
   - `REQUIREMENTS.md` — what is needed and why, scoped against `docs/SCOPE.md`.
   - `DESIGN.md` — how it will be built: modules touched, schema changes, data flow,
     interfaces to other modules, config/registry entries.
   - `TASKS.md` — the concrete task breakdown derived from the design.
   - `TRACKER.md` — one checkbox per task from `TASKS.md`, kept ticked live as work
     happens (not batched at the end).
3. Do not start writing code until at least `REQUIREMENTS.md` and `DESIGN.md` exist.
4. Never edit a previous requirement folder's `REQUIREMENTS.md`/`DESIGN.md` to widen its
   scope after the fact — open a new folder instead. Historical folders are a record of
   what was decided and when.

## Index

| Folder | Status | Summary |
|---|---|---|
| [`2026-08-27-repo-scaffold-and-governance`](2026-08-27-repo-scaffold-and-governance/) | ✅ Done | Documentation/governance scaffold: thesis, scope, architecture, AGENTS.md, changelog/status, requirements workflow itself |
| [`2026-08-27-phase1-spot-collector`](2026-08-27-phase1-spot-collector/) | 🟡 Implemented, live run pending | Spot instruments/margin metadata, trades, aggTrades, bookTicker, ticker, candles, depth sync/resync, health/audit, rate limiting -- built and tested against a local mock (real Binance unreachable from this sandbox); a live run is the one remaining acceptance criterion |
| [`2026-08-27-futures-and-options-collectors`](2026-08-27-futures-and-options-collectors/) | 🟡 Implemented, live run pending | USDS-M + COIN-M futures (funding, open interest, liquidations, mark price) built on Phase 1's shared framework; Options connector implemented raw-fidelity-only (disabled by default) pending live wire-format verification |
| [`2026-08-27-per-run-db-and-background-run-scripts`](2026-08-27-per-run-db-and-background-run-scripts/) | ✅ Done | Each start/stop cycle gets its own database file (`{run_id}` in config); `scripts/collector.sh` to start/stop/status/tail in the background |
| [`2026-08-27-positioning-coverage-tiers-and-timestamp-audit`](2026-08-27-positioning-coverage-tiers-and-timestamp-audit/) | ✅ Done | Futures long/short positioning data, explicit BROAD/HIGH_RESOLUTION coverage-tier tracking per symbol, and a source-vs-receive timestamp audit (fixed the missing `open_interest.observation_time`) -- from a pre-3-day-capture review |

Update this table whenever a folder is added or its status changes.
