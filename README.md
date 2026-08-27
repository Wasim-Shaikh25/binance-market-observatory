# Binance Market Observatory

A public-data-only collector for Binance market data (Spot, Margin metadata, USDⓈ-M
Futures, COIN-M Futures, Options), storing everything durably and faithfully in SQL for
future research. No API keys, no account access, no trading logic — see `docs/THESIS.md`
for the full reasoning and `docs/SCOPE.md` for the enforced boundary.

## Start here

| Document | Purpose |
|---|---|
| [`AGENTS.md`](AGENTS.md) | Rules for anyone (human or AI) working in this repo — read this first |
| [`docs/THESIS.md`](docs/THESIS.md) | Why this project exists, and every architectural decision made so far |
| [`docs/SCOPE.md`](docs/SCOPE.md) | Enforced in-scope / modify-on-sight / never-add checklist |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Living technical design: components, data flow, schema shape |
| [`docs/requirements/`](docs/requirements/) | Spec-driven work log — one folder per requirement (requirements → design → tasks → tracker) |
| [`CHANGELOG.md`](CHANGELOG.md) | What changed and why, most recent first |
| [`STATUS.md`](STATUS.md) | Current phase, what's done, what's next |

## Current status

All four products are implemented (`src/`) and tested end-to-end against a local mock
Binance server (41 tests, `tests/`) — see `STATUS.md` for the full picture. **Not yet
run against real Binance**: this project's development sandbox cannot reach Binance's
servers, so a live run from a machine with normal network access is the one remaining
step before the collector is considered done. See
`docs/requirements/2026-08-27-phase1-spot-collector/` and
`docs/requirements/2026-08-27-futures-and-options-collectors/` for details.

### Running it

```
pip install -r requirements.txt
python -m src.main                 # starts collecting; Ctrl-C for a graceful stop
python -m src.audit                # audits the most recent run (docs/THESIS.md #8)
python -m pytest                   # 41 tests, no network required (uses a local mock)
```

Each start gets its own database file: `config/settings.yaml`'s `database.path`
contains a `{run_id}` placeholder (a UTC timestamp), so stopping and starting again
begins a fresh `data/market_<run_id>.db` rather than appending to the last run.
`python -m src.audit` with no arguments always targets the most recently modified one.

### Running it in the background

```
scripts/collector.sh start    # launches detached, returns immediately
scripts/collector.sh status   # is it running?
scripts/collector.sh tail     # follow the current run's log
scripts/collector.sh stop     # graceful shutdown (SIGTERM), waits up to 30s
```

PID is tracked in `data/collector.pid`; logs land in `data/logs/run_<run_id>.log`,
one per run, matching that run's database file.

## Working in this repo

1. Read `AGENTS.md` and `CHANGELOG.md` before making any change.
2. Every unit of work gets its own folder under `docs/requirements/` — see
   `docs/requirements/README.md` for the convention.
3. Nothing on `docs/SCOPE.md`'s 🔴 list gets built here, ever.
