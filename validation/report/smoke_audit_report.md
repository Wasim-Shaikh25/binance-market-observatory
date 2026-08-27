# Collector Audit Report

Generated: 2026-08-27T08:36:40.840603+00:00

## Symbol coverage

- COINM_FUTURES: 65 distinct symbols observed
- SPOT: 3685 distinct symbols observed
- USDM_FUTURES: 877 distinct symbols observed

## Event counts by product / stream kind

- COINM_FUTURES / `btcusd_perp@bookTicker`: 18476
- COINM_FUTURES / `ethusd_perp@bookTicker`: 16581
- COINM_FUTURES / `ethusd_perp@trade`: 2130
- COINM_FUTURES / `ethusd_perp@depth@100ms`: 2062
- COINM_FUTURES / `btcusd_perp@depth@100ms`: 2052
- COINM_FUTURES / `ethusd_perp@aggTrade`: 1331
- COINM_FUTURES / `btcusd_perp@trade`: 979
- COINM_FUTURES / `btcusd_perp@aggTrade`: 514
- COINM_FUTURES / `ethusd_perp@markPrice@1s`: 376
- COINM_FUTURES / `btcusd_perp@markPrice@1s`: 376
- COINM_FUTURES / `ethusd_perp@kline_1m`: 203
- COINM_FUTURES / `btcusd_perp@kline_1m`: 123
- COINM_FUTURES / `!forceOrder@arr`: 109
- COINM_FUTURES / `ethusd_perp@ticker`: 91
- COINM_FUTURES / `btcusd_perp@ticker`: 79
- COINM_FUTURES / `exchangeInfo`: 30
- COINM_FUTURES / `topLongShortPositionRatio`: 8
- COINM_FUTURES / `topLongShortAccountRatio`: 8
- COINM_FUTURES / `openInterest`: 8
- COINM_FUTURES / `globalLongShortAccountRatio`: 8
- COINM_FUTURES / `coverage_tier`: 8
- COINM_FUTURES / `ethusd_perp@depth_snapshot`: 1
- COINM_FUTURES / `btcusd_perp@depth_snapshot`: 1
- SPOT / `btcusdt@bookTicker`: 38063
- SPOT / `ethusdt@bookTicker`: 35367
- SPOT / `ethusdt@trade`: 12540
- SPOT / `btcusdt@trade`: 12518
- SPOT / `ethusdt@aggTrade`: 5137
- SPOT / `exchangeInfo`: 3685
- SPOT / `btcusdt@aggTrade`: 3045
- SPOT / `ethusdt@depth@100ms`: 1801
- SPOT / `btcusdt@depth@100ms`: 1801
- SPOT / `ethusdt@ticker`: 143
- SPOT / `btcusdt@ticker`: 143
- SPOT / `ethusdt@kline_1m`: 73
- SPOT / `btcusdt@kline_1m`: 73
- SPOT / `coverage_tier`: 8
- SPOT / `ethusdt@depth_snapshot`: 2
- SPOT / `btcusdt@depth_snapshot`: 2
- USDM_FUTURES / `ethusdt@bookTicker`: 69646
- USDM_FUTURES / `btcusdt@bookTicker`: 64210
- USDM_FUTURES / `ethusdt@trade`: 16563
- USDM_FUTURES / `btcusdt@trade`: 4947
- USDM_FUTURES / `btcusdt@depth@100ms`: 1361
- USDM_FUTURES / `ethusdt@depth@100ms`: 1358
- USDM_FUTURES / `exchangeInfo`: 877
- USDM_FUTURES / `btcusdt@depth_snapshot`: 59
- USDM_FUTURES / `topLongShortPositionRatio`: 8
- USDM_FUTURES / `topLongShortAccountRatio`: 8
- USDM_FUTURES / `takerlongshortRatio`: 8
- USDM_FUTURES / `openInterest`: 8
- USDM_FUTURES / `globalLongShortAccountRatio`: 8
- USDM_FUTURES / `coverage_tier`: 8
- USDM_FUTURES / `ethusdt@depth_snapshot`: 5

## Duplicate / dropped writes

- COINM_FUTURES: 3109 raw trade events vs 3113 normalized rows (diff = duplicates or failed writes: -4)
- SPOT: 25078 raw trade events vs 25084 normalized rows (diff = duplicates or failed writes: -6)
- USDM_FUTURES: 21560 raw trade events vs 21647 normalized rows (diff = duplicates or failed writes: -87)

## Depth resyncs (update-ID gaps detected)

- USDM_FUTURES BTCUSDT: 1011 resyncs
- USDM_FUTURES ETHUSDT: 15 resyncs

## WebSocket reconnects

- ws_connected: 23
- ws_reconnect: 15

## REST failures

- rest_failure: 8

## Database write failures

- db_write_failure: 0

## Stale streams (no raw event in the last 10 minutes)

None.


## Coverage tiers (latest assignment per symbol)

- COINM_FUTURES HIGH_RESOLUTION: 2 symbols
- SPOT HIGH_RESOLUTION: 2 symbols
- USDM_FUTURES HIGH_RESOLUTION: 2 symbols

## Futures positioning data

- COINM_FUTURES / globalLongShortAccountRatio: 8 observations across 2 symbols
- COINM_FUTURES / topLongShortAccountRatio: 8 observations across 2 symbols
- COINM_FUTURES / topLongShortPositionRatio: 8 observations across 2 symbols
- USDM_FUTURES / globalLongShortAccountRatio: 8 observations across 2 symbols
- USDM_FUTURES / takerlongshortRatio: 8 observations across 2 symbols
- USDM_FUTURES / topLongShortAccountRatio: 8 observations across 2 symbols
- USDM_FUTURES / topLongShortPositionRatio: 8 observations across 2 symbols

## Storage

- market_smoke_live_20260827T140252Z.db: 245,096,448 bytes
- market_smoke_live_20260827T140252Z.db-wal: 53,646,552 bytes
- market_smoke_live_20260827T140252Z.db-shm: 131,072 bytes
