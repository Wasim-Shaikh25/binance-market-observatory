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

from .models import Envelope, taker_side
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
        "(exchange, product, symbol, stream_name, source_endpoint, schema_version, "
        "observed_at, payload_json) VALUES ('binance', ?, ?, ?, ?, ?, ?, ?)",
        (
            env.product,
            env.symbol,
            env.stream_name,
            env.source_endpoint,
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
        "price, quantity, trade_time, buyer_maker, taker_side, observed_at) "
        "VALUES ('binance', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            env.product,
            env.symbol,
            p["agg_trade_id"],
            p.get("first_trade_id"),
            p.get("last_trade_id"),
            p["price"],
            p["quantity"],
            p["trade_time"],
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
        "base_volume, quote_volume, open_time, close_time, first_trade_id, "
        "last_trade_id, trade_count, observed_at) "
        "VALUES ('binance', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
            p.get("first_trade_id"),
            p.get("last_trade_id"),
            p.get("trade_count"),
            env.observed_at,
        ),
    )


async def _write_candle(conn: aiosqlite.Connection, env: Envelope) -> None:
    p = env.payload
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
        "(exchange, product, symbol, last_update_id, bids_json, asks_json, observed_at) "
        "VALUES ('binance', ?, ?, ?, ?, ?, ?)",
        (
            env.product,
            env.symbol,
            p["last_update_id"],
            json.dumps(p["bids"], separators=(",", ":")),
            json.dumps(p["asks"], separators=(",", ":")),
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
        "INSERT INTO open_interest (exchange, product, symbol, open_interest, observed_at) "
        "VALUES ('binance', ?, ?, ?, ?)",
        (env.product, env.symbol, p["open_interest"], env.observed_at),
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
        "estimated_settle_price, funding_rate, next_funding_time, observed_at) "
        "VALUES ('binance', ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            env.product,
            env.symbol,
            p["mark_price"],
            p.get("index_price"),
            p.get("estimated_settle_price"),
            p.get("funding_rate"),
            p.get("next_funding_time"),
            env.observed_at,
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
}


class DBWriter:
    """Drains an asyncio.Queue of Envelopes and is the sole writer to SQLite."""

    def __init__(self, conn: aiosqlite.Connection, queue: "asyncio.Queue[Envelope]"):
        self._conn = conn
        self._queue = queue
        self._stop = False

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
            finally:
                self._queue.task_done()

    def stop(self) -> None:
        self._stop = True
