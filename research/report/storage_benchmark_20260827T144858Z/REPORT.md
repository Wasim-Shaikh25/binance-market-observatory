# Storage format benchmark (one DB file)

- Generated (UTC): `20260827T144858Z`
- Source DB: `data/market_smoke_complete_20260827T174743Z.db`
- Period: `2026-08-27T12:17:43.455770+00:00` → `2026-08-27T12:22:50.742299+00:00`
- raw_events rows: **166,621**

## Sizes

| Representation | Size (MiB) | Notes |
|---|---:|---|
| SQLite (db+wal+shm) | 107.72 | Current collector store (raw+normalized+indexes) |
| Raw NDJSON (payloads only) | 29.58 | Uncompressed wire-ish JSON lines (166,621 lines) |
| Raw NDJSON + gzip | 2.93 | Same payloads, gzip -6 |
| Parquet+ZSTD (normalized tables) | 3.39 | trades, agg_trades, book_ticker, candles, depth_updates, ticker_24h, mark_price |
| Parquet+ZSTD (raw_events incl. payload_json) | 3.36 | Evidence column retained |
| ClickHouse | N/A | Not installed on this host |

## Ratios vs SQLite

- **raw NDJSON**: 3.64× vs SQLite (+72.5% size change; negative = larger than SQLite)
- **raw NDJSON+gzip**: 36.72× vs SQLite (+97.3% size change; negative = larger than SQLite)
- **Parquet normalized**: 31.78× vs SQLite (+96.9% size change; negative = larger than SQLite)
- **Parquet raw_events**: 32.04× vs SQLite (+96.9% size change; negative = larger than SQLite)
- **Parquet norm + raw_events**: 15.95× vs SQLite (+93.7% size change; negative = larger than SQLite)

## Per-table Parquet+ZSTD

| Table | MiB |
|---|---:|
| book_ticker | 1.706 |
| depth_updates | 0.915 |
| trades | 0.443 |
| agg_trades | 0.219 |
| ticker_24h | 0.064 |
| mark_price | 0.035 |
| candles | 0.008 |

## Interpretation

- SQLite holds **raw + normalized + indexes** in one file — that is why it can
  look large vs a single Parquet of typed columns alone.
- A fair 'same evidence' archive is roughly **gzipped raw NDJSON** (or
  Parquet of `raw_events`) **plus** Parquet of normalized tables — not
  Parquet-normalized alone.
- ClickHouse was **not** measured here (no server/client). Install and re-run
  after the planned multi-hour capture if you want a CH number.
- This does **not** change the live collector. Migration stays: measure → decide.

## Artifacts

- `research/report/storage_benchmark_20260827T144858Z/artifacts/`

