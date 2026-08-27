# Design: Per-Run Database Files + Background Run Scripts

## Run ID

A run ID is a UTC timestamp, `%Y%m%dT%H%M%SZ` (e.g. `20260827T153045Z`), generated once
per process start. `src/main.py` takes it from the `RUN_ID` environment variable if
set (so `scripts/collector.sh` can generate one, use it for the log filename, and have
Python's database filename match it for easy correlation), or generates its own
otherwise (so `python -m src.main` still works standalone without the script).

## Path template

`src/config.py` gains `resolve_db_path(template, run_id)`: if the template contains
`{run_id}`, it's substituted; otherwise the template is returned unchanged. This keeps
every existing caller that passes a fixed path (all current tests) working without
modification -- the placeholder is opt-in via the config value, not a new required
argument threaded through the codebase. `config/settings.yaml`'s default
`database.path` becomes `data/market_{run_id}.db`.

`src/main.py`'s `run()` resolves the path once at startup and logs it prominently
(`Run <id> starting. Writing to database: <path>`) so it's the first thing visible in
the log file regardless of how the process was started.

## Audit: finding the right file

`src/audit.py` adds `--db <path>` to target a specific run explicitly. Without it,
`find_latest_db_path(template)` in `src/config.py` globs the template with `{run_id}`
replaced by `*` and returns the most recently modified match (falling back to the
template itself if it contains no placeholder, or `None` if nothing matches yet).

## Background run scripts

One script, `scripts/collector.sh`, rather than three separate ones, since start/stop/
status/tail all share the same PID-file and log-directory conventions and splitting
them would just duplicate that:

- `start`: refuses to start a second instance (checks the PID file), generates a run
  ID, launches `python -m src.main` via `nohup` with `RUN_ID` exported and stdout/
  stderr redirected to `data/logs/run_<id>.log`, records the PID in `data/collector.pid`,
  and echoes the resolved database path back by grepping the first log line.
- `stop`: sends SIGTERM to the recorded PID -- `main.py` already installs a SIGTERM
  handler that triggers its existing graceful-shutdown path (cancel connectors, drain
  the writer queue, close the DB cleanly) -- then polls for up to 30s for the process
  to exit before giving up (not force-killing automatically, since a stuck shutdown is
  worth investigating rather than papering over).
- `status` / `tail`: read-only conveniences over the same PID file / log directory.

No process supervisor, log rotation, or multi-instance support -- not asked for, and
`nohup` + a PID file is the minimum that satisfies "run from a terminal and leave it
running."

## Non-goals

- Changing the database schema, connectors, or rate limiting -- purely operational.
- Windows support for the shell script (the project's target environment is Linux/macOS
  per the existing sandbox and typical deployment target for this kind of collector).
