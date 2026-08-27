========================================
BINANCE MARKET OBSERVATORY
DATA CAPTURE AUDIT
========================================

Generated: 2026-08-27T16:57:46.494885+00:00
Database: `data/market_smoke_chprim_20260827T222300Z.db` (95,174,656 bytes)
Period start (raw_events): 2026-08-27T16:54:09.575048+00:00
Period end (raw_events): 2026-08-27T16:57:09.549694+00:00

This report validates **data availability, integrity, timestamps,
synchronization, provenance, and storage correctness** only.
It does **not** evaluate profitability, strategies, signals, AI, or market behavior.

========================================
PRODUCT SUMMARY
========================================

SPOT: ✅ PASS
MARGIN METADATA: ✅ PASS
USDⓈ-M: ✅ PASS
COIN-M: ✅ PASS
OPTIONS: ✅ PASS

========================================
DATA TYPE COVERAGE
========================================

Trades                       ✅ PASS
AggTrades                    ✅ PASS
BookTicker                   ✅ PASS
Depth                        ✅ PASS
Candles                      ✅ PASS
Ticker                       ✅ PASS
Mark Price                   ✅ PASS
Funding                      ✅ PASS
Open Interest                ✅ PASS
Liquidations                 ✅ PASS
Positioning Statistics       ✅ PASS
Options                      🟡 PARTIAL
Instrument Metadata          ✅ PASS
Margin Metadata              ✅ PASS
Raw payloads                 ✅ PASS
Provenance                   ✅ PASS
Timestamps                   ✅ PASS
System health                ✅ PASS
Database integrity           ✅ PASS
Coverage                     ✅ PASS
Reconciliations              🟡 PARTIAL
Storage                      ✅ PASS

========================================
VALIDATION MATRIX
========================================

| Product | Data | Public? | Implemented? | Enabled? | Final | Notes |
|---|---|---|---|---|---|---|
| SPOT | instruments | True | True | True | ✅ PASS |  |
| SPOT | trades | True | True | True | ✅ PASS |  |
| SPOT | agg_trades | True | True | True | ✅ PASS |  |
| SPOT | book_ticker | True | True | True | ✅ PASS | No Binance event timestamp on this stream |
| SPOT | depth | True | True | True | ✅ PASS | Top-N / rotating; not all symbols |
| SPOT | candles | True | True | True | ✅ PASS | Intervals from config only |
| SPOT | ticker_24h | True | True | True | ✅ PASS |  |
| MARGIN | metadata | True | True | True | ✅ PASS | margin_tradable on Spot instrument_snapshots |
| USDM_FUTURES | instruments | True | True | True | ✅ PASS |  |
| USDM_FUTURES | trades | True | True | True | ✅ PASS |  |
| USDM_FUTURES | agg_trades | True | True | True | ✅ PASS |  |
| USDM_FUTURES | book_ticker | True | True | True | ✅ PASS | No Binance event timestamp |
| USDM_FUTURES | depth | True | True | True | ✅ PASS | Top-N |
| USDM_FUTURES | candles | True | True | True | ✅ PASS |  |
| USDM_FUTURES | ticker_24h | True | True | True | ✅ PASS |  |
| USDM_FUTURES | mark_price | True | True | True | ✅ PASS | Includes index + estimated funding fields |
| USDM_FUTURES | funding | True | True | True | ✅ PASS | From markPrice stream = estimated/current, not settled history |
| USDM_FUTURES | open_interest | True | True | True | ✅ PASS |  |
| USDM_FUTURES | liquidations | True | True | True | ✅ PASS |  |
| USDM_FUTURES | positioning | True | True | True | ✅ PASS |  |
| COINM_FUTURES | instruments | True | True | True | ✅ PASS |  |
| COINM_FUTURES | trades | True | True | True | ✅ PASS |  |
| COINM_FUTURES | agg_trades | True | True | True | ✅ PASS |  |
| COINM_FUTURES | book_ticker | True | True | True | ✅ PASS | No Binance event timestamp |
| COINM_FUTURES | depth | True | True | True | ✅ PASS | Top-N |
| COINM_FUTURES | candles | True | True | True | ✅ PASS |  |
| COINM_FUTURES | ticker_24h | True | True | True | ✅ PASS |  |
| COINM_FUTURES | mark_price | True | True | True | ✅ PASS |  |
| COINM_FUTURES | funding | True | True | True | ✅ PASS | Estimated/current from markPrice |
| COINM_FUTURES | open_interest | True | True | True | ✅ PASS |  |
| COINM_FUTURES | liquidations | True | True | True | ✅ PASS |  |
| COINM_FUTURES | positioning | True | True | True | ✅ PASS | Uses pair=; takerBuySellVol not takerlongshortRatio |
| OPTIONS | instruments | True | True | True | ✅ PASS | exchangeInfo → instruments + snapshots |
| OPTIONS | trades | True | True | True | ✅ PASS | REST /eapi/v1/trades; WS best-effort |
| OPTIONS | book | True | True | True | ✅ PASS | REST /eapi/v1/depth → depth_snapshots (poll, not WS sync) |
| OPTIONS | ticker | True | True | True | ✅ PASS | REST /eapi/v1/ticker → ticker_24h |
| OPTIONS | open_interest | True | True | True | ✅ PASS | REST /eapi/v1/openInterest → open_interest |
| OPTIONS | iv_greeks | True | True | True | ✅ PASS | REST /eapi/v1/mark → options_mark (IV+greeks as text) |
| EXCHANGE | system_status | True | True | True | ✅ PASS | Public /sapi/v1/system/status → exchange_status |
| EXCHANGE | announcements | False | False | True | ⚫ NOT_PUBLICLY_AVAILABLE | No stable public machine-readable feed in scope |
| EXCHANGE | rest_backfill_provenance | True | True | True | ✅ PASS | raw_events.source_type = websocket|rest_poll|rest_backfill; gap_fill crawler for agg_trades/klines |

========================================
DETAILED CHECKS
========================================

### database

- ✅ **PASS** — opens + WAL: journal_mode=wal; file exists=True
- ✅ **PASS** — required tables: all present

### decimal_precision

- ✅ **PASS** — price/qty columns are TEXT: no REAL/FLOAT/DOUBLE on price columns
- ✅ **PASS** — trade price samples non-null: sampled 20 prices; null/empty=0

### products

- ✅ **PASS** — SPOT: enabled; instruments=3685; raw_events=88098
- ✅ **PASS** — USDM_FUTURES: enabled; instruments=877; raw_events=9903
- ✅ **PASS** — COINM_FUTURES: enabled; instruments=30; raw_events=27852
- ✅ **PASS** — OPTIONS: raw_events=149; instruments=2; trades=40; options_mark=6; options_index=3
- ✅ **PASS** — MARGIN metadata (via Spot): spot_instruments=3685; margin_tradable=1 → 794; null status=0

### instruments

- ✅ **PASS** — SPOT: instruments=3685; snapshots=3685; trading≈1358; inactive≈2327; tick_size=3685; step_size=3685; base=3685; quote=3685; first=2026-08-27T16:54:10.031185+00:00; last=2026-08-27T16:54:10.050477+00:00
- ✅ **PASS** — USDM_FUTURES: instruments=877; snapshots=877; trading≈746; inactive≈131; tick_size=877; step_size=877; base=877; quote=877; first=2026-08-27T16:54:10.082364+00:00; last=2026-08-27T16:54:10.086348+00:00
- ✅ **PASS** — COINM_FUTURES: instruments=30; snapshots=30; trading≈0; inactive≈0; tick_size=30; step_size=30; base=30; quote=30; first=2026-08-27T16:54:10.199760+00:00; last=2026-08-27T16:54:10.199760+00:00
- ✅ **PASS** — historical snapshots possible: instruments with >1 snapshot row so far: 0 (schema supports history; multi-row only appears after metadata changes / re-polls)
- ✅ **PASS** — OPTIONS: options instruments stored=2

### raw_events

- ✅ **PASS** — existence + provenance columns: rows=126003; null_payload=0; null_product=0
- ✅ **PASS** — count by product: COINM_FUTURES=27852, EXCHANGE=1, OPTIONS=149, SPOT=88098, USDM_FUTURES=9903
- ✅ **PASS** — random payload JSON validity (n=50): invalid_json=0/50
- ✅ **PASS** — receive timestamp (observed_at): observed_at required NOT NULL on schema; stream_name + source_endpoint preserved

### trades

- ✅ **PASS** — SPOT: rows=21051; unique(symbol,trade_id)=21051; dup≈0; null_price/qty=0; null_buyer_maker=0; earliest_ms=1787849651017; latest_ms=1787849825349
- ✅ **PASS** — USDM_FUTURES: rows=2828; unique(symbol,trade_id)=2828; dup≈0; null_price/qty=0; null_buyer_maker=0; earliest_ms=1787849651111; latest_ms=1787849829763
- ✅ **PASS** — COINM_FUTURES: rows=1057; unique(symbol,trade_id)=1057; dup≈0; null_price/qty=0; null_buyer_maker=0; earliest_ms=1787849652376; latest_ms=1787849829297
- ✅ **PASS** — OPTIONS: rows=40 (REST /eapi/v1/trades)

### agg_trades

- ✅ **PASS** — SPOT: rows=4561; with first/last trade id=4561
- ✅ **PASS** — USDM_FUTURES: rows=1100; with first/last trade id=1100
- ✅ **PASS** — COINM_FUTURES: rows=712; with first/last trade id=712

### book_ticker

- ✅ **PASS** — SPOT: rows=56483; null/negative=0; severe_cross_sample=0; note: Binance bookTicker has no exchange event timestamp (observed_at only)
- ✅ **PASS** — USDM_FUTURES: rows=2733; null/negative=0; severe_cross_sample=0; note: Binance bookTicker has no exchange event timestamp (observed_at only)
- ✅ **PASS** — COINM_FUTURES: rows=23329; null/negative=0; severe_cross_sample=0; note: Binance bookTicker has no exchange event timestamp (observed_at only)
- ⚪ **NOT_IMPLEMENTED** — OPTIONS: Options uses REST ticker, not bookTicker stream

### depth

- ✅ **PASS** — SPOT: depth_symbols≈1; snapshots=1; updates=1791; depth_resync events=0 (gaps detected & recorded, not silent)
- ✅ **PASS** — USDM_FUTURES: depth_symbols≈2; snapshots=2; updates=896; depth_resync events=0 (gaps detected & recorded, not silent)
- ✅ **PASS** — COINM_FUTURES: depth_symbols≈2; snapshots=7; updates=1628; depth_resync events=5 (gaps detected & recorded, not silent)
- ✅ **PASS** — OPTIONS: depth_snapshots=6 (REST /eapi/v1/depth polls; no WS depth sync)

### depth_coverage

- ✅ **PASS** — symbol_coverage tiers: COINM_FUTURES/BROAD=1; COINM_FUTURES/HIGH_RESOLUTION=1; SPOT/BROAD=1; SPOT/HIGH_RESOLUTION=1; USDM_FUTURES/BROAD=1; USDM_FUTURES/HIGH_RESOLUTION=1
- ✅ **PASS** — full-universe depth claim: both BROAD and HIGH_RESOLUTION tiers present (top-N depth + non-depth symbols)

### candles

- ✅ **PASS** — configured intervals present: configured=['1m']; found=['1m']; counts={'1m': 24}
- ⚪ **NOT_IMPLEMENTED** — interval 15m: not in config kline_intervals (add there to collect)
- ⚪ **NOT_IMPLEMENTED** — interval 4h: not in config kline_intervals (add there to collect)
- ⚪ **NOT_IMPLEMENTED** — interval 1d: not in config kline_intervals (add there to collect)
- ✅ **PASS** — OHLC invariants: rows=24; ohlc_violations=0
- ✅ **PASS** — final vs in-progress flag: is_final=1 → 18; is_final=0 → 6

### ticker_24h

- ✅ **PASS** — SPOT: rows=348; symbols=2
- ✅ **PASS** — USDM_FUTURES: rows=178; symbols=2
- ✅ **PASS** — COINM_FUTURES: rows=125; symbols=2
- ✅ **PASS** — OPTIONS: rows=6 (REST /eapi/v1/ticker)

### mark_price

- ✅ **PASS** — USDM_FUTURES: rows=358; with_index_price=358; with_event_time=358; funding_rate on mark_price = estimated/current (not settled)
- ✅ **PASS** — COINM_FUTURES: rows=358; with_index_price=358; with_event_time=358; funding_rate on mark_price = estimated/current (not settled)

### funding

- ✅ **PASS** — USDM_FUTURES: rows=358 (derived from markPrice stream — estimated/current, not historical settled series)
- ✅ **PASS** — COINM_FUTURES: rows=358 (derived from markPrice stream — estimated/current, not historical settled series)

### open_interest

- ✅ **PASS** — USDM_FUTURES: rows=3; observation_time present; median_gap_ms=60906.0; p95_gap_ms=60894; largest_gap_ms=60918
- ✅ **PASS** — COINM_FUTURES: rows=3; observation_time present; median_gap_ms=60877.0; p95_gap_ms=58879; largest_gap_ms=62875

### liquidations

- ✅ **PASS** — USDM_FUTURES: events=14; last_event_ms=1787849802467; forceOrder_raw=14
- ✅ **PASS** — COINM_FUTURES: events=53; last_event_ms=1787849828664; forceOrder_raw=53

### positioning

- ✅ **PASS** — USDM_FUTURES: globalLongShortAccountRatio: rows=3 symbols=2; takerlongshortRatio: rows=3 symbols=2; topLongShortAccountRatio: rows=3 symbols=2; topLongShortPositionRatio: rows=3 symbols=2
- ✅ **PASS** — COINM_FUTURES: globalLongShortAccountRatio: rows=3 symbols=2; takerBuyVol: rows=3 symbols=2; takerSellVol: rows=3 symbols=2; topLongShortAccountRatio: rows=3 symbols=2; topLongShortPositionRatio: rows=3 symbols=2

### options

- ✅ **PASS** — instruments: instruments=2
- ✅ **PASS** — trades: trades=40 (REST /eapi/v1/trades)
- ✅ **PASS** — ticker: ticker_24h=6 (REST /eapi/v1/ticker)
- ✅ **PASS** — iv_greeks: options_mark=6; with_mark_iv=6
- ✅ **PASS** — index: options_index=3
- ✅ **PASS** — book: depth_snapshots=6 (REST /eapi/v1/depth polls)
- ✅ **PASS** — open_interest: open_interest rows=6 (REST /eapi/v1/openInterest)
- 🟡 **PARTIAL** — ws: ws_raw_events=0 (REST is primary; WS best-effort — may be 0 on this network)

### exchange_wide

- ✅ **PASS** — system status / maintenance feed: rows=1; last status_code=0 msg='normal' at 2026-08-27T16:54:09.764278+00:00

### timestamps

- ✅ **PASS** — trades event vs receive: sampled=200; missing_observed_at=0; recv<<event anomalies=0
- ✅ **PASS** — open_interest source vs receive distinct: sampled=12; near-identical source/receive pairs=0 (should usually differ — poll lag)
- ⚫ **NOT_PUBLICLY_AVAILABLE** — book_ticker source timestamp: Binance bookTicker payload has no event time — only observed_at stored (documented)
- ✅ **PASS** — collector host clock UTC-aware: datetime.now(timezone.utc) ok; local epoch_ms≈1787849866268; NTP not verified from inside process — confirm OS time sync operationally

### system_health

- ✅ **PASS** — ws_connected: count=9
- ✅ **PASS** — ws_reconnect: count=6 (informational)
- ✅ **PASS** — rest_failure: count=0 (clean)
- ✅ **PASS** — db_write_failure: count=0 (clean)
- ✅ **PASS** — depth_resync: count=5 (informational)

### raw_vs_normalized

- ✅ **PASS** — trades sample: checked=6; matched_price_qty_id=6
- ✅ **PASS** — futures_positioning payload_json: sampled=20; valid_with_value=20

### reconciliation

- ✅ **PASS** — trades↔candle: USDM_FUTURES BTCUSDT 1m@1787849760000: trades_in_db=576; matches OHLC/vol/count within tolerance
- 🟡 **PARTIAL** — depth↔bookTicker: missing bookTicker or empty book

### coverage_matrix

- ✅ **PASS** — SPOT: universe≈2; trades=2; book=2; candles=2; depth_symbols=1 (expected ≤ universe; top-N); missing_trades_sample=[]; missing_book_sample=[]; instruments_table=3685 (may include full exchangeInfo even in list mode)
- ✅ **PASS** — USDM_FUTURES: universe≈2; trades=2; book=2; candles=2; depth_symbols=2 (expected ≤ universe; top-N); missing_trades_sample=[]; missing_book_sample=[]; instruments_table=877 (may include full exchangeInfo even in list mode)
- ✅ **PASS** — COINM_FUTURES: universe≈2; trades=2; book=2; candles=2; depth_symbols=2 (expected ≤ universe; top-N); missing_trades_sample=[]; missing_book_sample=[]; instruments_table=30 (may include full exchangeInfo even in list mode)

### storage

- ✅ **PASS** — growth estimate: db_bytes=95,174,656; tracked_rows≈245609; hours≈0.049992957222222224; rows_per_hour≈4912872.005315682; by_table={'raw_events': 126003, 'trades': 24976, 'agg_trades': 6373, 'book_ticker': 82545, 'candles': 24, 'depth_updates': 4315, 'ticker_24h': 657, 'mark_price': 716}; projections={'7d': {'rows': 825362496, 'bytes': 319831894259}, '30d': {'rows': 3537267843, 'bytes': 1370708118253}, '90d': {'rows': 10611803531, 'bytes': 4112124354760}, '1y': {'rows': 43036758766, 'bytes': 16676948772084}} (smoke/list rates do not equal full-universe rates)

### provenance

- ✅ **PASS** — REST backfill source_type: source_type counts={'internal': 32, 'rest_poll': 4785, 'websocket': 121186}; gap_fill_jobs=0; values=websocket|rest_poll|rest_backfill — crawler fills agg_trades/klines holes

### coverage_history

- ✅ **PASS** — explicit started_at/ended_at/reason: rows=10; open=6; with_reason=10

========================================
FIVE QUESTIONS
========================================

### A. What did we intend to collect?

Per `docs/THESIS.md` / `config/settings.yaml`: Spot, USDS-M, COIN-M public
market data (trades, aggTrades, bookTicker, ticker, klines, depth top-N,
instruments+margin metadata, futures mark/funding/OI/liquidations/positioning),
plus `raw_events`. Options: REST instruments/trades/ticker/mark(IV)/index/depth/OI when enabled; WS best-effort. Exchange system status polled publicly. `raw_events.source_type` records websocket vs rest_poll vs rest_backfill.

### B. What does Binance actually expose publicly?

See inventory matrix (`publicly_available` column). Based on Binance's
documented public REST/WS surfaces — not a live docs scrape.

### C. What did our code actually collect?

See product summary + detailed checks against this database file.
Configured products enabled: ['spot', 'usdm_futures', 'coinm_futures', 'options'].

### D. How much of it is trustworthy?

Integrity checks: decimal TEXT columns, raw payload JSON samples,
timestamp separation, duplicate trade IDs, depth resync recording,
WS/REST system_events, optional trade↔candle and depth↔bookTicker reconciliations.
Event-driven completeness cannot be proven 100% without exchange reconciliation —
classify confidence from continuity evidence, not row counts alone.

### E. What are we missing?

- ⚪ NOT_IMPLEMENTED: candles/interval 15m — not in config kline_intervals (add there to collect)
- ⚪ NOT_IMPLEMENTED: candles/interval 4h — not in config kline_intervals (add there to collect)
- ⚪ NOT_IMPLEMENTED: candles/interval 1d — not in config kline_intervals (add there to collect)
- 🟡 PARTIAL: options/ws — ws_raw_events=0 (REST is primary; WS best-effort — may be 0 on this network)
- ⚫ NOT_PUBLICLY_AVAILABLE: matrix/EXCHANGE / announcements — No stable public machine-readable feed in scope

========================================
NOTHING-MISSING CHECKLIST
========================================

- [x] Spot: ✅ PASS
- [x] Margin metadata: ✅ PASS
- [x] USDⓈ-M Futures: ✅ PASS
- [x] COIN-M Futures: ✅ PASS
- [x] Options: ✅ PASS
- [x] Instruments: ✅ PASS
- [x] Trades: ✅ PASS
- [x] Aggregate trades: ✅ PASS
- [x] BookTicker: ✅ PASS
- [x] Order book depth: ✅ PASS
- [x] Candles: ✅ PASS
- [x] Ticker: ✅ PASS
- [x] Mark price: ✅ PASS
- [x] Funding: ✅ PASS
- [x] Open interest: ✅ PASS
- [x] Liquidations: ✅ PASS
- [x] Public positioning: ✅ PASS
- [x] Raw payloads: ✅ PASS
- [x] Timestamps: ✅ PASS
- [x] System events / health: ✅ PASS
- [x] Symbol coverage / tiers: ✅ PASS
- [x] Database integrity: ✅ PASS
- [x] Storage growth: ✅ PASS

## Research-readiness note

Per-symbol research readiness is implied by `symbol_coverage` tiers
(`BROAD` vs `HIGH_RESOLUTION`) plus the feed matrix above.
Do **not** treat BROAD symbols as having full depth.

## Final question

> For any supported Binance symbol and timestamp in our collection period,
> can we tell exactly what public data we captured, what we did not, and why?

**Partial** — see FAIL/PARTIAL/NOT_IMPLEMENTED items above.
