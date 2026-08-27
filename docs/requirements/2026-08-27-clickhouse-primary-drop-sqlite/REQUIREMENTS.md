# Requirements: ClickHouse primary, drop durable SQLite

**Opened:** 2026-08-27  
**Scope check:** In scope — storage durability and validation only (`docs/SCOPE.md`).

## Why

Dual-write smoke showed ClickHouse ~15× smaller than SQLite for the same capture.
SQLite should no longer be the durable store once CH + zstd archive cover the full
normalized + raw surface.

## What

1. ClickHouse sink writes **all** normalized kinds (not only trades/agg/book_ticker)
   plus `raw_events`, prices as String.
2. SQLite may still exist for in-process ops (gap-fill reads, system_events) during a
   run, but is **not durable** when `database.persist: false` (file removed after
   graceful stop if CH and/or archive is enabled).
3. Smoke config: CH + archive on, persist off; delete leftover local `data/*.db`.
4. One live smoke + validation checklist (`python -m src.validate`) must still PASS
   the intended Binance capture matrix (Options WS / announcements caveats unchanged).

## Acceptance

- Full CH table set mirrors collector kinds used in `storage._NORMALIZERS`
- Smoke run completes; checklist report written under `validation/report/`
- Local smoke SQLite files cleaned up after the run when persist is false
- Tests updated; CHANGELOG / STATUS / ARCHITECTURE updated
