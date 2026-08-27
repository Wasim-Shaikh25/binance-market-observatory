# Requirement: Per-Run Database Files + Background Run Scripts

**Opened:** 2026-08-27
**Status:** Done

## Why

The user asked two operational questions after Phase 1's implementation landed:

1. Every time the collector is started and stopped, it should produce its own data
   file for that run -- starting it again should begin a fresh file, not keep
   appending to the same one.
2. How to run it in the background from a terminal and leave it running, and how to
   stop it cleanly.

Neither was addressed by the initial implementation: `config/settings.yaml` pointed at
a single fixed `data/market.db`, and there was no documented/scripted way to run the
process detached from a terminal.

## What is needed

- The configured database path supports a `{run_id}` placeholder; each run substitutes
  its own start-time-based run ID, so consecutive start/stop cycles produce separate
  files (`data/market_<run_id>.db`) without any code change required to opt in.
- Backward compatible: a path with no `{run_id}` placeholder still works unchanged
  (existing tests configure a fixed tmp-file path and must keep passing).
- `src/audit.py` can be pointed at an explicit run's database, or default to the most
  recently modified one matching the configured pattern, so "audit the run I just did"
  doesn't require remembering the exact filename.
- A single script (`scripts/collector.sh`) to start (detached, logging to its own
  per-run log file), stop (graceful SIGTERM, matching `main.py`'s existing signal
  handling), check status, and tail the current log -- so the user can run this from a
  terminal and walk away.

## Out of scope for this requirement

- A process supervisor (systemd unit, Docker, etc.) -- the user asked for "run from
  terminal and leave it running," which `nohup` + a PID file satisfies; a supervisor is
  a reasonable future upgrade but wasn't asked for.
- Automatic log rotation/retention -- one log file per run is created; cleaning up old
  ones is left to the user for now.

## Acceptance criteria

- [x] Starting the collector twice in a row (stop, then start again) produces two
      distinct database files.
- [x] Existing tests that configure a fixed database path (no placeholder) still pass
      unchanged.
- [x] `python -m src.audit` with no arguments finds and reports on the most recent run
      automatically; `--db <path>` overrides it explicitly.
- [x] `scripts/collector.sh start|stop|status|tail` works: start detaches and returns
      immediately, stop sends SIGTERM and waits for clean shutdown, status reports
      running/not-running, tail follows the current run's log.
- [x] `README.md` documents the workflow.
