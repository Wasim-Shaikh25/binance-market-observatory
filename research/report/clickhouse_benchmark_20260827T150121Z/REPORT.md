# ClickHouse readable storage benchmark

- Generated (UTC): `20260827T150121Z`
- Source DB: `data/market_smoke_complete_20260827T174743Z.db`
- Period: `2026-08-27T12:17:43.455770+00:00` -> `2026-08-27T12:22:50.742299+00:00`
- raw_events rows (SQLite): **166,621**
- ClickHouse HTTP: `http://127.0.0.1:8123/` database `bmo_bench`

## Size comparison

| Store | Size (MiB) | Notes |
|---|---:|---|
| SQLite (db+wal+shm) | 107.72 | Current collector |
| **ClickHouse (active parts)** | **9.52** | MergeTree on disk, includes raw_events |

- ClickHouse is **11.31x** smaller than this SQLite file (**91.2%** fewer bytes).
- Prices remain **String** (exact decimal text), payloads remain **readable JSON strings**.

## ClickHouse per-table disk

| Table | Rows | bytes_on_disk (MiB) | compressed (MiB) | uncompressed (MiB) |
|---|---:|---:|---:|---:|
| raw_events | 166,621 | 5.854 | 5.852 | 46.992 |
| book_ticker | 108,315 | 1.448 | 1.446 | 11.421 |
| depth_updates | 7,536 | 1.400 | 1.399 | 4.743 |
| trades | 32,747 | 0.462 | 0.461 | 4.038 |
| agg_trades | 8,310 | 0.243 | 0.243 | 1.011 |
| ticker_24h | 1,101 | 0.073 | 0.072 | 0.239 |
| mark_price | 1,226 | 0.039 | 0.038 | 0.164 |
| candles | 36 | 0.005 | 0.004 | 0.006 |

## Loaded row counts

| Table | Rows loaded |
|---|---:|
| agg_trades | 8,310 |
| book_ticker | 108,315 |
| candles | 36 |
| depth_updates | 7,536 |
| mark_price | 1,226 |
| raw_events | 166,621 |
| ticker_24h | 1,101 |
| trades | 32,747 |

## Readability checks (live SELECT)

### Latest trades
```
   ┌─product─┬─symbol──┬───trade_id─┬─price──────────┬─quantity───┬─taker_side─┬─observed_at──────────────────────┐
1. │ SPOT    │ BTCUSDT │ 6626196286 │ 79517.12000000 │ 0.00012000 │ BUY        │ 2026-08-27T12:22:50.684909+00:00 │
2. │ SPOT    │ BTCUSDT │ 6626196285 │ 79517.12000000 │ 0.00069000 │ BUY        │ 2026-08-27T12:22:50.563637+00:00 │
3. │ SPOT    │ ETHUSDT │ 4311454375 │ 2504.90000000  │ 0.02560000 │ SELL       │ 2026-08-27T12:22:50.447604+00:00 │
   └─────────┴─────────┴────────────┴────────────────┴────────────┴────────────┴──────────────────────────────────┘
```

### book_ticker counts by product
```
   ┌─product───────┬─────n─┐
1. │ COINM_FUTURES │ 30732 │
2. │ SPOT          │ 75134 │
3. │ USDM_FUTURES  │  2449 │
   └───────────────┴───────┘
```

### Raw payload still readable (prefix)
```
   ┌─product─┬─stream_name───┬─payload_prefix─────────────┐
1. │ SPOT    │ coverage_tier │ {"tier":"HIGH_RESOLUTION"} │
2. │ SPOT    │ coverage_tier │ {"tier":"BROAD"}           │
   └─────────┴───────────────┴────────────────────────────┘
```

### Price type stays exact text
```
   ┌─price───┬─toTypeName(price)─┐
1. │ 79380.5 │ String            │
   └─────────┴───────────────────┘
```

## Ops notes

- Container: `docker start|stop bmo-clickhouse`
- This benchmark does **not** switch the live collector off SQLite.
- Fair long-term design remains: compressed raw archive + ClickHouse hot + Parquet cold.

