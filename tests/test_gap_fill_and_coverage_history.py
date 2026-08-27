"""Gap-fill helpers and coverage_history / backfill write safety."""

from __future__ import annotations

import asyncio

from src.gap_fill import find_id_gaps, find_open_time_gaps, parse_kline_rest
from src.models import Envelope
from src.storage import DBWriter, open_db


def test_find_id_gaps_skips_huge_holes():
    assert find_id_gaps([1, 2, 3, 5, 6]) == [(4, 4)]
    assert find_id_gaps([1, 100000]) == []  # capped


def test_find_open_time_gaps_1m():
    step = 60_000
    times = [0, step, 3 * step]
    assert find_open_time_gaps(times, step) == [(2 * step, 2 * step)]


def test_parse_kline_rest():
    row = [1000, "1", "2", "0.5", "1.5", "10", 1599, "100", 7, "4", "40"]
    parsed = parse_kline_rest(row, "1m")
    assert parsed["open_time"] == 1000
    assert parsed["close"] == "1.5"
    assert parsed["is_final"] is True


async def test_coverage_history_open_and_close(tmp_path):
    conn = await open_db(str(tmp_path / "ch.db"))
    queue: asyncio.Queue = asyncio.Queue()
    writer = DBWriter(conn, queue)
    task = asyncio.create_task(writer.run())
    await queue.put(
        Envelope(
            product="SPOT",
            stream_name="coverage_history",
            source_endpoint="internal",
            kind="coverage_history",
            payload={
                "action": "open",
                "feed": "DEPTH",
                "tier": "HIGH_RESOLUTION",
                "started_at": "2026-08-27T10:00:00+00:00",
                "reason": "entered_top_n",
            },
            symbol="BTCUSDT",
        )
    )
    await queue.put(
        Envelope(
            product="SPOT",
            stream_name="coverage_history",
            source_endpoint="internal",
            kind="coverage_history",
            payload={
                "action": "close",
                "feed": "DEPTH",
                "ended_at": "2026-08-28T04:00:00+00:00",
                "close_reason": "left_top_n",
            },
            symbol="BTCUSDT",
        )
    )
    await queue.put(None)
    await task
    cur = await conn.execute(
        "SELECT tier, started_at, ended_at, reason, close_reason FROM coverage_history"
    )
    row = await cur.fetchone()
    assert row == (
        "HIGH_RESOLUTION",
        "2026-08-27T10:00:00+00:00",
        "2026-08-28T04:00:00+00:00",
        "entered_top_n",
        "left_top_n",
    )
    await conn.close()


async def test_rest_backfill_does_not_overwrite_live_candle_or_agg(tmp_path):
    conn = await open_db(str(tmp_path / "bf.db"))
    queue: asyncio.Queue = asyncio.Queue()
    writer = DBWriter(conn, queue)
    task = asyncio.create_task(writer.run())
    live_candle = Envelope(
        product="SPOT",
        stream_name="btcusdt@kline_1m",
        source_endpoint="wss://stream.binance.com:9443",
        kind="candle",
        payload={
            "interval": "1m",
            "open_time": 1000,
            "close_time": 1599,
            "open": "1",
            "high": "2",
            "low": "1",
            "close": "LIVE",
            "base_volume": "1",
            "quote_volume": "1",
            "is_final": True,
        },
        symbol="BTCUSDT",
    )
    backfill_candle = Envelope(
        product="SPOT",
        stream_name="rest_backfill_klines",
        source_endpoint="https://api.binance.com/api/v3/klines",
        kind="candle",
        payload={**live_candle.payload, "close": "BACKFILL"},
        symbol="BTCUSDT",
        source_type="rest_backfill",
    )
    live_agg = Envelope(
        product="SPOT",
        stream_name="btcusdt@aggTrade",
        source_endpoint="wss://stream.binance.com:9443",
        kind="agg_trade",
        payload={
            "agg_trade_id": 9,
            "first_trade_id": 1,
            "last_trade_id": 1,
            "price": "1",
            "quantity": "1",
            "trade_time": 1,
            "buyer_maker": False,
        },
        symbol="BTCUSDT",
    )
    backfill_agg = Envelope(
        product="SPOT",
        stream_name="rest_backfill_aggTrades",
        source_endpoint="https://api.binance.com/api/v3/aggTrades",
        kind="agg_trade",
        payload={**live_agg.payload, "price": "99"},
        symbol="BTCUSDT",
        source_type="rest_backfill",
    )
    for env in (live_candle, backfill_candle, live_agg, backfill_agg):
        await queue.put(env)
    await queue.put(None)
    await task

    cur = await conn.execute("SELECT close FROM candles WHERE open_time=1000")
    assert (await cur.fetchone())[0] == "LIVE"
    cur = await conn.execute("SELECT price FROM agg_trades WHERE agg_trade_id=9")
    assert (await cur.fetchone())[0] == "1"
    cur = await conn.execute(
        "SELECT source_type, COUNT(*) FROM raw_events GROUP BY source_type ORDER BY 1"
    )
    by_type = {r[0]: r[1] for r in await cur.fetchall()}
    assert by_type["websocket"] == 2
    assert by_type["rest_backfill"] == 2
    await conn.close()
