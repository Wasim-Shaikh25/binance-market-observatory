# Tracker: Per-Run Database Files + Background Run Scripts

- [x] 1. `resolve_db_path` / `find_latest_db_path` added to `src/config.py`
- [x] 2. `config/settings.yaml` default changed to `data/market_{run_id}.db`
- [x] 3. `src/main.py` generates/reads `RUN_ID`, resolves the path, logs it at startup
- [x] 4. `src/audit.py` accepts `--db`, otherwise auto-discovers the latest run
- [x] 5. `scripts/collector.sh` written and made executable
- [x] 6. Unit tests written (`tests/test_run_id.py`, 6 tests)
- [x] 7. `README.md` updated with the run/stop workflow
- [x] 8. `CHANGELOG.md`, `STATUS.md`, this tracker updated

**Status:** Done. Verified live in this sandbox: two consecutive
`scripts/collector.sh start` / `stop` cycles produced two distinct database files
(`data/market_<run_id>.db`) and two distinct log files, `status` correctly reported
running/not-running, `stop` cleanly terminated via SIGTERM within seconds each time,
and `python -m src.audit` with no arguments correctly picked the most recently
modified run. (Actual data collection during that smoke test was empty/failing as
expected -- this sandbox still can't reach Binance -- but that's outside this
requirement's scope; see the Phase 1 and futures/options trackers.)
