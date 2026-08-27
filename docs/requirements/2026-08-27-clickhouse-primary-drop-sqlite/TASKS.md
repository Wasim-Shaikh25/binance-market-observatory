# Tasks

1. Expand `ClickHouseSink` DDL + `_norm_line` to all normalizer kinds.
2. Add `database.persist` config; delete SQLite after stop when appropriate.
3. Update smoke/settings defaults (CH + archive on for smoke; persist false).
4. Delete leftover `data/*.db` smoke files.
5. Live smoke (~3 min) → validate checklist → confirm CH counts → docs.
6. Tests for full CH enqueue mapping + persist flag.
