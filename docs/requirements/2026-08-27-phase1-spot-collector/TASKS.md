# Tasks: Phase 1 — Spot Collector

1. Lock the open decisions in `DESIGN.md` (libraries, batch size, registry schema,
   kline intervals) and update that file.
2. Scaffold `src/` per `docs/ARCHITECTURE.md` §7 (`connectors/`, `storage/`,
   `registry/`, `health/`), plus `config/` and `tests/`.
3. Implement `storage/schema.py`: SQLite DDL for `raw_events`, `instruments`,
   `instrument_snapshots`, `trades`, `agg_trades`, `book_ticker`, `ticker_24h`,
   `candles`, `depth_snapshots`/`depth_updates`, `health`, `system_events`. All
   decimal-bearing columns as `TEXT`.
4. Implement `storage/queue.py` and `storage/writer.py` (single writer, WAL mode).
5. Implement `registry/` loader and the initial Spot capability registry entries.
6. Implement `connectors/spot/instruments.py` (exchangeInfo poll + snapshot diffing).
7. Implement `connectors/spot` trade/aggTrade/bookTicker/ticker/candle stream handling.
8. Implement the depth snapshot + WebSocket sync + gap-detection resync state machine,
   driven by the depth config (top-N/ranking/refresh).
9. Implement reconnect/backoff for all WebSocket connections.
10. Implement `health/` counters, rollup job, and `system_events` writes for every
    reconnect, resync, and REST failure.
11. Write tests: at minimum, depth gap-detection/resync, envelope shape validation,
    decimal-as-text enforcement, and a forced-disconnect reconnect test.
12. Run the collector continuously; write the 72-hour audit report per
    `THESIS.md` §8 once the run completes clean.
13. Update `docs/ARCHITECTURE.md` §6 and §7 to match what was actually built.
14. Update `docs/requirements/README.md` index to mark this folder Done.
15. Keep `TRACKER.md` in this folder current as each task completes.
