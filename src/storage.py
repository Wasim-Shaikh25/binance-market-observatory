"""Single DB writer: drains the internal queue, writes raw_events plus any
applicable normalized row in one transaction per envelope. This is the only
component that opens write transactions against SQLite (docs/ARCHITECTURE.md
#3) -- WAL mode + a single writer, never multiple concurrent writers.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

import aiosqlite

from .models import Envelope, resolve_source_type, taker_side
from .schema import init_schema

logger = logging.getLogger(__name__)


async def open_db(path: str) -> aiosqlite.Connection:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = await aiosqlite.connect(path)
    await conn.execute("PRAGMA journal_mode=WAL;")
    await conn.execute("PRAGMA synchronous=NORMAL;")
    await conn.execute("PRAGMA foreign_keys=ON;")
    await init_schema(conn)
    return conn


async def log_system_event(
    conn: aiosqlite.Connection,
    event_type: str,
    detail: str = "",
    product: str | None = None,
    symbol: str | None = None,
) -> None:
    from .models import now_iso

    await conn.execute(
        "INSERT INTO system_events (product, symbol, event_type, detail, observed_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (product, symbol, event_type, detail, now_iso()),
    )
    await conn.commit()


async def _write_raw(conn: aiosqlite.Connection, env: Envelope) -> None:
    await conn.execute(
        "INSERT INTO raw_events "
        "(exchange, product, symbol, stream_name, source_endpoint, source_type, "
        "schema_version, observed_at, payload_json) VALUES ('binance', ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            env.product,
            env.symbol,
            env.stream_name,
            env.source_endpoint,
            resolve_source_type(env),
            env.schema_version,
            env.observed_at,
            json.dumps(env.payload, separators=(",", ":")),
        ),
    )


async def _write_trade(conn: aiosqlite.Connection, env: Envelope) -> None:
    p = env.payload
    buyer_maker = bool(p["buyer_maker"])
    await conn.execute(
        "INSERT OR IGNORE INTO trades "
        "(exchange, product, symbol, trade_id, event_time, trade_time, price, "
        "quantity, quote_quantity, buyer_maker, taker_side, observed_at) "
        "VALUES ('binance', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            env.product,
            env.symbol,
            p["trade_id"],
            p.get("event_time"),
            p["trade_time"],
            p["price"],
            p["quantity"],
            p.get("quote_quantity"),
            int(buyer_maker),
            taker_side(buyer_maker),
            env.observed_at,
        ),
    )


async def _write_agg_trade(conn: aiosqlite.Connection, env: Envelope) -> None:
    p = env.payload
    buyer_maker = bool(p["buyer_maker"])
    await conn.execute(
        "INSERT OR IGNORE INTO agg_trades "
        "(exchange, product, symbol, agg_trade_id, first_trade_id, last_trade_id, "
        "price, quantity, trade_time, event_time, buyer_maker, taker_side, observed_at) "
        "VALUES ('binance', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            env.product,
            env.symbol,
            p["agg_trade_id"],
            p.get("first_trade_id"),
            p.get("last_trade_id"),
            p["price"],
            p["quantity"],
            p["trade_time"],
            p.get("event_time"),
            int(buyer_maker),
            taker_side(buyer_maker),
            env.observed_at,
        ),
    )


async def _write_book_ticker(conn: aiosqlite.Connection, env: Envelope) -> None:
    p = env.payload
    await conn.execute(
        "INSERT INTO book_ticker "
        "(exchange, product, symbol, update_id, best_bid_price, best_bid_qty, "
        "best_ask_price, best_ask_qty, observed_at) VALUES ('binance', ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            env.product,
            env.symbol,
            p.get("update_id"),
            p["best_bid_price"],
            p["best_bid_qty"],
            p["best_ask_price"],
            p["best_ask_qty"],
            env.observed_at,
        ),
    )


async def _write_ticker_24h(conn: aiosqlite.Connection, env: Envelope) -> None:
    p = env.payload
    await conn.execute(
        "INSERT INTO ticker_24h "
        "(exchange, product, symbol, price_change, price_change_percent, "
        "weighted_avg_price, last_price, open_price, high_price, low_price, "
        "base_volume, quote_volume, open_time, close_time, event_time, first_trade_id, "
        "last_trade_id, trade_count, observed_at) "
        "VALUES ('binance', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            env.product,
            env.symbol,
            p.get("price_change"),
            p.get("price_change_percent"),
            p.get("weighted_avg_price"),
            p.get("last_price"),
            p.get("open_price"),
            p.get("high_price"),
            p.get("low_price"),
            p.get("base_volume"),
            p.get("quote_volume"),
            p.get("open_time"),
            p.get("close_time"),
            p.get("event_time"),
            p.get("first_trade_id"),
            p.get("last_trade_id"),
            p.get("trade_count"),
            env.observed_at,
        ),
    )


async def _write_candle(conn: aiosqlite.Connection, env: Envelope) -> None:
    p = env.payload
    # Live WS may REPLACE in-progress bars. Backfill must NEVER overwrite an
    # existing live observation for the same (symbol, interval, open_time).
    if resolve_source_type(env) == "rest_backfill":
        await conn.execute(
            "INSERT OR IGNORE INTO candles "
            "(exchange, product, symbol, interval, open_time, close_time, open, high, "
            "low, close, base_volume, quote_volume, trade_count, taker_buy_base_volume, "
            "taker_buy_quote_volume, is_final, observed_at) "
            "VALUES ('binance', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                env.product,
                env.symbol,
                p["interval"],
                p["open_time"],
                p["close_time"],
                p["open"],
                p["high"],
                p["low"],
                p["close"],
                p["base_volume"],
                p["quote_volume"],
                p.get("trade_count"),
                p.get("taker_buy_base_volume"),
                p.get("taker_buy_quote_volume"),
                int(bool(p.get("is_final", False))),
                env.observed_at,
            ),
        )
        return
    await conn.execute(
        "INSERT OR REPLACE INTO candles "
        "(exchange, product, symbol, interval, open_time, close_time, open, high, "
        "low, close, base_volume, quote_volume, trade_count, taker_buy_base_volume, "
        "taker_buy_quote_volume, is_final, observed_at) "
        "VALUES ('binance', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            env.product,
            env.symbol,
            p["interval"],
            p["open_time"],
            p["close_time"],
            p["open"],
            p["high"],
            p["low"],
            p["close"],
            p["base_volume"],
            p["quote_volume"],
            p.get("trade_count"),
            p.get("taker_buy_base_volume"),
            p.get("taker_buy_quote_volume"),
            int(bool(p.get("is_final", False))),
            env.observed_at,
        ),
    )


async def _write_depth_snapshot(conn: aiosqlite.Connection, env: Envelope) -> None:
    p = env.payload
    await conn.execute(
        "INSERT INTO depth_snapshots "
        "(exchange, product, symbol, last_update_id, bids_json, asks_json, "
        "event_time, transaction_time, observed_at) VALUES ('binance', ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            env.product,
            env.symbol,
            p["last_update_id"],
            json.dumps(p["bids"], separators=(",", ":")),
            json.dumps(p["asks"], separators=(",", ":")),
            p.get("event_time"),
            p.get("transaction_time"),
            env.observed_at,
        ),
    )


async def _write_depth_update(conn: aiosqlite.Connection, env: Envelope) -> None:
    p = env.payload
    await conn.execute(
        "INSERT INTO depth_updates "
        "(exchange, product, symbol, first_update_id, final_update_id, bids_json, "
        "asks_json, event_time, observed_at) VALUES ('binance', ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            env.product,
            env.symbol,
            p["first_update_id"],
            p["final_update_id"],
            json.dumps(p["bids"], separators=(",", ":")),
            json.dumps(p["asks"], separators=(",", ":")),
            p.get("event_time"),
            env.observed_at,
        ),
    )


async def _write_instrument_snapshot(conn: aiosqlite.Connection, env: Envelope) -> None:
    p = env.payload
    await conn.execute(
        "INSERT OR IGNORE INTO instruments (exchange, product, symbol) VALUES ('binance', ?, ?)",
        (env.product, env.symbol),
    )
    cur = await conn.execute(
        "SELECT id FROM instruments WHERE exchange='binance' AND product=? AND symbol=?",
        (env.product, env.symbol),
    )
    row = await cur.fetchone()
    instrument_id = row[0]
    await conn.execute(
        "INSERT INTO instrument_snapshots "
        "(instrument_id, observed_at, status, base_asset, quote_asset, contract_type, "
        "tick_size, step_size, min_qty, min_notional, margin_tradable, payload_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            instrument_id,
            env.observed_at,
            p.get("status"),
            p.get("base_asset"),
            p.get("quote_asset"),
            p.get("contract_type"),
            p.get("tick_size"),
            p.get("step_size"),
            p.get("min_qty"),
            p.get("min_notional"),
            int(bool(p.get("margin_tradable", False))) if "margin_tradable" in p else None,
            json.dumps(p, separators=(",", ":")),
        ),
    )


async def _write_funding_rate(conn: aiosqlite.Connection, env: Envelope) -> None:
    p = env.payload
    await conn.execute(
        "INSERT INTO funding_rate (exchange, product, symbol, funding_rate, funding_time, "
        "mark_price, observed_at) VALUES ('binance', ?, ?, ?, ?, ?, ?)",
        (env.product, env.symbol, p["funding_rate"], p["funding_time"], p.get("mark_price"), env.observed_at),
    )


async def _write_open_interest(conn: aiosqlite.Connection, env: Envelope) -> None:
    p = env.payload
    await conn.execute(
        "INSERT INTO open_interest (exchange, product, symbol, open_interest, "
        "observation_time, observed_at) VALUES ('binance', ?, ?, ?, ?, ?)",
        (env.product, env.symbol, p["open_interest"], p.get("observation_time"), env.observed_at),
    )


async def _write_futures_positioning(conn: aiosqlite.Connection, env: Envelope) -> None:
    p = env.payload
    await conn.execute(
        "INSERT INTO futures_positioning (exchange, product, symbol, metric, value, "
        "observation_time, source_endpoint, observed_at, payload_json) "
        "VALUES ('binance', ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            env.product,
            env.symbol,
            p["metric"],
            p["value"],
            p.get("observation_time"),
            env.source_endpoint,
            env.observed_at,
            json.dumps(p.get("raw", {}), separators=(",", ":")),
        ),
    )


async def _write_symbol_coverage(conn: aiosqlite.Connection, env: Envelope) -> None:
    p = env.payload
    await conn.execute(
        "INSERT INTO symbol_coverage (product, symbol, tier, observed_at) VALUES (?, ?, ?, ?)",
        (env.product, env.symbol, p["tier"], env.observed_at),
    )


async def _write_coverage_history(conn: aiosqlite.Connection, env: Envelope) -> None:
    p = env.payload
    action = p.get("action", "open")
    if action == "close":
        await conn.execute(
            """
            UPDATE coverage_history
            SET ended_at = ?, close_reason = ?
            WHERE product = ? AND symbol = ? AND feed = ? AND ended_at IS NULL
            """,
            (
                p.get("ended_at", env.observed_at),
                p.get("close_reason") or p.get("reason"),
                env.product,
                env.symbol,
                p.get("feed", "DEPTH"),
            ),
        )
        return
    await conn.execute(
        """
        INSERT INTO coverage_history
        (product, symbol, feed, tier, started_at, ended_at, reason, close_reason)
        VALUES (?, ?, ?, ?, ?, NULL, ?, NULL)
        """,
        (
            env.product,
            env.symbol,
            p.get("feed", "DEPTH"),
            p["tier"],
            p.get("started_at", env.observed_at),
            p["reason"],
        ),
    )


async def _write_gap_fill_job(conn: aiosqlite.Connection, env: Envelope) -> None:
    p = env.payload
    await conn.execute(
        """
        INSERT INTO gap_fill_jobs
        (product, symbol, feed, gap_start, gap_end, status, rows_inserted, detail, observed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            env.product,
            env.symbol,
            p["feed"],
            p.get("gap_start"),
            p.get("gap_end"),
            p["status"],
            int(p.get("rows_inserted") or 0),
            p.get("detail"),
            env.observed_at,
        ),
    )


async def _write_liquidation(conn: aiosqlite.Connection, env: Envelope) -> None:
    p = env.payload
    await conn.execute(
        "INSERT INTO liquidations (exchange, product, symbol, side, order_type, price, "
        "avg_price, quantity, order_status, event_time, observed_at) "
        "VALUES ('binance', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            env.product,
            env.symbol,
            p["side"],
            p.get("order_type"),
            p["price"],
            p.get("avg_price"),
            p["quantity"],
            p.get("order_status"),
            p.get("event_time"),
            env.observed_at,
        ),
    )


async def _write_mark_price(conn: aiosqlite.Connection, env: Envelope) -> None:
    p = env.payload
    await conn.execute(
        "INSERT INTO mark_price (exchange, product, symbol, mark_price, index_price, "
        "estimated_settle_price, funding_rate, next_funding_time, event_time, observed_at) "
        "VALUES ('binance', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            env.product,
            env.symbol,
            p["mark_price"],
            p.get("index_price"),
            p.get("estimated_settle_price"),
            p.get("funding_rate"),
            p.get("next_funding_time"),
            p.get("event_time"),
            env.observed_at,
        ),
    )


async def _write_exchange_status(conn: aiosqlite.Connection, env: Envelope) -> None:
    p = env.payload
    await conn.execute(
        "INSERT INTO exchange_status (status_code, msg, observed_at, payload_json) VALUES (?, ?, ?, ?)",
        (p.get("status"), p.get("msg"), env.observed_at, json.dumps(p.get("raw", p), separators=(",", ":"))),
    )


async def _write_options_mark(conn: aiosqlite.Connection, env: Envelope) -> None:
    p = env.payload
    await conn.execute(
        "INSERT INTO options_mark (exchange, product, symbol, mark_price, mark_iv, bid_iv, ask_iv, "
        "delta, gamma, theta, vega, observed_at, payload_json) "
        "VALUES ('binance', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            env.product,
            env.symbol,
            p.get("mark_price"),
            p.get("mark_iv"),
            p.get("bid_iv"),
            p.get("ask_iv"),
            p.get("delta"),
            p.get("gamma"),
            p.get("theta"),
            p.get("vega"),
            env.observed_at,
            json.dumps(p.get("raw", {}), separators=(",", ":")),
        ),
    )


async def _write_options_index(conn: aiosqlite.Connection, env: Envelope) -> None:
    p = env.payload
    await conn.execute(
        "INSERT INTO options_index (exchange, product, underlying, index_price, observation_time, "
        "observed_at, payload_json) VALUES ('binance', ?, ?, ?, ?, ?, ?)",
        (
            env.product,
            p["underlying"],
            p["index_price"],
            p.get("observation_time"),
            env.observed_at,
            json.dumps(p.get("raw", {}), separators=(",", ":")),
        ),
    )


_NORMALIZERS = {
    "trade": _write_trade,
    "agg_trade": _write_agg_trade,
    "book_ticker": _write_book_ticker,
    "ticker_24h": _write_ticker_24h,
    "candle": _write_candle,
    "depth_snapshot": _write_depth_snapshot,
    "depth_update": _write_depth_update,
    "instrument_snapshot": _write_instrument_snapshot,
    "funding_rate": _write_funding_rate,
    "open_interest": _write_open_interest,
    "liquidation": _write_liquidation,
    "mark_price": _write_mark_price,
    "futures_positioning": _write_futures_positioning,
    "symbol_coverage": _write_symbol_coverage,
    "coverage_history": _write_coverage_history,
    "gap_fill_job": _write_gap_fill_job,
    "exchange_status": _write_exchange_status,
    "options_mark": _write_options_mark,
    "options_index": _write_options_index,
}


class DBWriter:
    """Drains an asyncio.Queue of Envelopes and is the sole writer to SQLite.

    Optional dual sinks (raw zstd archive, ClickHouse) run best-effort after
    SQLite commit so a sink failure never rolls back durable SQLite evidence.
    """

    def __init__(
        self,
        conn: aiosqlite.Connection,
        queue: "asyncio.Queue[Envelope]",
        raw_archive=None,
        clickhouse=None,
    ):
        self._conn = conn
        self._queue = queue
        self._stop = False
        self._raw_archive = raw_archive
        self._clickhouse = clickhouse

    async def run(self) -> None:
        while not self._stop:
            env = await self._queue.get()
            if env is None:  # sentinel
                self._queue.task_done()
                break
            try:
                await _write_raw(self._conn, env)
                normalizer = _NORMALIZERS.get(env.kind)
                if normalizer is not None:
                    await normalizer(self._conn, env)
                await self._conn.commit()
            except Exception as exc:  # noqa: BLE001 - must not crash the writer
                await self._conn.rollback()
                logger.exception("DB write failed for kind=%s stream=%s", env.kind, env.stream_name)
                await log_system_event(
                    self._conn,
                    "db_write_failure",
                    detail=f"{type(exc).__name__}: {exc}",
                    product=env.product,
                    symbol=env.symbol,
                )
            else:
                if self._raw_archive is not None:
                    try:
                        self._raw_archive.append(env)
                    except Exception as exc:  # noqa: BLE001
                        logger.exception("raw archive write failed")
                        await log_system_event(
                            self._conn,
                            "archive_write_failure",
                            detail=f"{type(exc).__name__}: {exc}",
                            product=env.product,
                            symbol=env.symbol,
                        )
                if self._clickhouse is not None:
                    try:
                        await self._clickhouse.enqueue(env)
                    except Exception as exc:  # noqa: BLE001
                        logger.exception("clickhouse write failed")
                        await log_system_event(
                            self._conn,
                            "clickhouse_write_failure",
                            detail=f"{type(exc).__name__}: {exc}",
                            product=env.product,
                            symbol=env.symbol,
                        )
            finally:
                self._queue.task_done()

        if self._clickhouse is not None:
            try:
                await self._clickhouse.close()
            except Exception:  # noqa: BLE001
                logger.exception("clickhouse flush/close failed")
        if self._raw_archive is not None:
            try:
                self._raw_archive.close()
            except Exception:  # noqa: BLE001
                logger.exception("raw archive close failed")

    def stop(self) -> None:
        self._stop = True
