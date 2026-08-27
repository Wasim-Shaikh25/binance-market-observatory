# Tasks: Per-Run Database Files + Background Run Scripts

1. Add `resolve_db_path` and `find_latest_db_path` to `src/config.py`.
2. Update `config/settings.yaml`'s `database.path` default to `data/market_{run_id}.db`
   with a comment explaining the placeholder.
3. Update `src/main.py` to generate/read a run ID, resolve the path, and log it clearly
   at startup.
4. Update `src/audit.py` to accept `--db` and otherwise auto-discover the latest run.
5. Write `scripts/collector.sh` (start/stop/status/tail) and make it executable.
6. Unit-test `resolve_db_path` and `find_latest_db_path`.
7. Update `README.md` with the run/stop workflow.
8. Update `CHANGELOG.md`, `STATUS.md`, and this folder's `TRACKER.md`.
