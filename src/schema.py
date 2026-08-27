"""SQLite DDL for the observatory database.

All price/quantity/decimal columns are TEXT (canonical decimal strings) per
docs/THESIS.md -- never floating point. Every row that represents market data
carries `product` and `symbol` so records for different Binance products
(SPOT, USDM_FUTURES, COINM_FUTURES, OPTIONS) are always identifiable without
having to parse `stream_name`.
"""

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS raw_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exchange TEXT NOT NULL DEFAULT 'binance',
    product TEXT NOT NULL,
    symbol TEXT,
    stream_name TEXT NOT NULL,
    source_endpoint TEXT NOT NULL,
    schema_version TEXT NOT NULL DEFAULT '1',
    observed_at TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_raw_events_product_symbol_time
    ON raw_events(product, symbol, observed_at);
CREATE INDEX IF NOT EXISTS idx_raw_events_stream
    ON raw_events(stream_name, observed_at);

CREATE TABLE IF NOT EXISTS instruments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exchange TEXT NOT NULL DEFAULT 'binance',
    product TEXT NOT NULL,
    symbol TEXT NOT NULL,
    UNIQUE(exchange, product, symbol)
);

CREATE TABLE IF NOT EXISTS instrument_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    instrument_id INTEGER NOT NULL REFERENCES instruments(id),
    observed_at TEXT NOT NULL,
    status TEXT,
    base_asset TEXT,
    quote_asset TEXT,
    contract_type TEXT,
    tick_size TEXT,
    step_size TEXT,
    min_qty TEXT,
    min_notional TEXT,
    margin_tradable INTEGER,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_instrument_snapshots_instrument_time
    ON instrument_snapshots(instrument_id, observed_at);

CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exchange TEXT NOT NULL DEFAULT 'binance',
    product TEXT NOT NULL,
    symbol TEXT NOT NULL,
    trade_id INTEGER NOT NULL,
    event_time INTEGER,
    trade_time INTEGER NOT NULL,
    price TEXT NOT NULL,
    quantity TEXT NOT NULL,
    quote_quantity TEXT,
    buyer_maker INTEGER NOT NULL,
    taker_side TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    UNIQUE(exchange, product, symbol, trade_id)
);
CREATE INDEX IF NOT EXISTS idx_trades_symbol_time ON trades(product, symbol, trade_time);

CREATE TABLE IF NOT EXISTS agg_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exchange TEXT NOT NULL DEFAULT 'binance',
    product TEXT NOT NULL,
    symbol TEXT NOT NULL,
    agg_trade_id INTEGER NOT NULL,
    first_trade_id INTEGER,
    last_trade_id INTEGER,
    price TEXT NOT NULL,
    quantity TEXT NOT NULL,
    trade_time INTEGER NOT NULL,
    buyer_maker INTEGER NOT NULL,
    taker_side TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    UNIQUE(exchange, product, symbol, agg_trade_id)
);
CREATE INDEX IF NOT EXISTS idx_agg_trades_symbol_time ON agg_trades(product, symbol, trade_time);

CREATE TABLE IF NOT EXISTS book_ticker (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exchange TEXT NOT NULL DEFAULT 'binance',
    product TEXT NOT NULL,
    symbol TEXT NOT NULL,
    update_id INTEGER,
    best_bid_price TEXT NOT NULL,
    best_bid_qty TEXT NOT NULL,
    best_ask_price TEXT NOT NULL,
    best_ask_qty TEXT NOT NULL,
    observed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_book_ticker_symbol_time ON book_ticker(product, symbol, observed_at);

CREATE TABLE IF NOT EXISTS ticker_24h (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exchange TEXT NOT NULL DEFAULT 'binance',
    product TEXT NOT NULL,
    symbol TEXT NOT NULL,
    price_change TEXT,
    price_change_percent TEXT,
    weighted_avg_price TEXT,
    last_price TEXT,
    open_price TEXT,
    high_price TEXT,
    low_price TEXT,
    base_volume TEXT,
    quote_volume TEXT,
    open_time INTEGER,
    close_time INTEGER,
    first_trade_id INTEGER,
    last_trade_id INTEGER,
    trade_count INTEGER,
    observed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ticker_24h_symbol_time ON ticker_24h(product, symbol, observed_at);

CREATE TABLE IF NOT EXISTS candles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exchange TEXT NOT NULL DEFAULT 'binance',
    product TEXT NOT NULL,
    symbol TEXT NOT NULL,
    interval TEXT NOT NULL,
    open_time INTEGER NOT NULL,
    close_time INTEGER NOT NULL,
    open TEXT NOT NULL,
    high TEXT NOT NULL,
    low TEXT NOT NULL,
    close TEXT NOT NULL,
    base_volume TEXT NOT NULL,
    quote_volume TEXT NOT NULL,
    trade_count INTEGER,
    taker_buy_base_volume TEXT,
    taker_buy_quote_volume TEXT,
    is_final INTEGER NOT NULL,
    observed_at TEXT NOT NULL,
    UNIQUE(exchange, product, symbol, interval, open_time)
);
CREATE INDEX IF NOT EXISTS idx_candles_symbol_interval_time
    ON candles(product, symbol, interval, open_time);

CREATE TABLE IF NOT EXISTS depth_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exchange TEXT NOT NULL DEFAULT 'binance',
    product TEXT NOT NULL,
    symbol TEXT NOT NULL,
    last_update_id INTEGER NOT NULL,
    bids_json TEXT NOT NULL,
    asks_json TEXT NOT NULL,
    observed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_depth_snapshots_symbol_time
    ON depth_snapshots(product, symbol, observed_at);

CREATE TABLE IF NOT EXISTS depth_updates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exchange TEXT NOT NULL DEFAULT 'binance',
    product TEXT NOT NULL,
    symbol TEXT NOT NULL,
    first_update_id INTEGER NOT NULL,
    final_update_id INTEGER NOT NULL,
    bids_json TEXT NOT NULL,
    asks_json TEXT NOT NULL,
    event_time INTEGER,
    observed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_depth_updates_symbol_time
    ON depth_updates(product, symbol, final_update_id);

CREATE TABLE IF NOT EXISTS funding_rate (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exchange TEXT NOT NULL DEFAULT 'binance',
    product TEXT NOT NULL,
    symbol TEXT NOT NULL,
    funding_rate TEXT NOT NULL,
    funding_time INTEGER NOT NULL,
    mark_price TEXT,
    observed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_funding_rate_symbol_time ON funding_rate(product, symbol, funding_time);

CREATE TABLE IF NOT EXISTS open_interest (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exchange TEXT NOT NULL DEFAULT 'binance',
    product TEXT NOT NULL,
    symbol TEXT NOT NULL,
    open_interest TEXT NOT NULL,
    observed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_open_interest_symbol_time ON open_interest(product, symbol, observed_at);

CREATE TABLE IF NOT EXISTS liquidations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exchange TEXT NOT NULL DEFAULT 'binance',
    product TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    order_type TEXT,
    price TEXT NOT NULL,
    avg_price TEXT,
    quantity TEXT NOT NULL,
    order_status TEXT,
    event_time INTEGER,
    observed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_liquidations_symbol_time ON liquidations(product, symbol, event_time);

CREATE TABLE IF NOT EXISTS mark_price (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exchange TEXT NOT NULL DEFAULT 'binance',
    product TEXT NOT NULL,
    symbol TEXT NOT NULL,
    mark_price TEXT NOT NULL,
    index_price TEXT,
    estimated_settle_price TEXT,
    funding_rate TEXT,
    next_funding_time INTEGER,
    observed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mark_price_symbol_time ON mark_price(product, symbol, observed_at);

CREATE TABLE IF NOT EXISTS health (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product TEXT NOT NULL,
    stream_name TEXT,
    symbol TEXT,
    metric TEXT NOT NULL,
    value REAL NOT NULL,
    observed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_health_product_metric_time ON health(product, metric, observed_at);

CREATE TABLE IF NOT EXISTS system_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product TEXT,
    symbol TEXT,
    event_type TEXT NOT NULL,
    detail TEXT,
    observed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_system_events_type_time ON system_events(event_type, observed_at);
"""


async def init_schema(conn) -> None:
    await conn.executescript(SCHEMA_SQL)
    await conn.commit()
