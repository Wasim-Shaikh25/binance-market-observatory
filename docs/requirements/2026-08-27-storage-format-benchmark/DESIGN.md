# Design

`research/script/benchmark_storage_formats.py`:

1. Open one `.db`
2. Report SQLite file bytes (+ WAL if present)
3. Stream `raw_events.payload_json` → NDJSON file; also gzip
4. Export `trades`, `agg_trades`, `book_ticker`, `candles`, `depth_updates`,
   `ticker_24h`, `mark_price` to Parquet (ZSTD) via pyarrow
5. Optional: Parquet of raw_events key columns + payload_json for apples-to-apples
6. Write markdown summary with ratios vs SQLite

Outputs under `research/report/storage_benchmark_<stamp>/`.
