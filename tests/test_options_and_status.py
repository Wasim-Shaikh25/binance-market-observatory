"""Options parsers + exchange_status / options_mark / options_index / depth / OI writers."""

from __future__ import annotations

import asyncio

from src.connectors.options import (
    option_symbol_parts,
    parse_option_depth,
    parse_option_mark,
    parse_option_open_interest,
    parse_option_symbol,
    parse_option_ticker,
    parse_option_trade,
)
from src.models import Envelope, resolve_source_type
from src.storage import DBWriter, open_db


async def _write_all(conn, envelopes):
    queue: asyncio.Queue = asyncio.Queue()
    writer = DBWriter(conn, queue)
    task = asyncio.create_task(writer.run())
    for env in envelopes:
        await queue.put(env)
    await queue.put(None)
    await task


def test_parse_option_symbol_keeps_strike_and_side():
    raw = {
        "symbol": "BTC-260828-65000-C",
        "status": "TRADING",
        "underlying": "BTCUSDT",
        "quoteAsset": "USDT",
        "side": "CALL",
        "strikePrice": "65000",
        "expiryDate": 1777334400000,
        "filters": [{"filterType": "PRICE_FILTER", "tickSize": "0.1"}],
    }
    parsed = parse_option_symbol(raw)
    assert parsed["contract_type"] == "CALL"
    assert parsed["strike_price"] == "65000"
    assert parsed["tick_size"] == "0.1"


def test_parse_option_trade_and_mark_as_strings():
    trade = parse_option_trade({"tradeId": 9, "price": "12.5", "qty": "0.1", "time": 1000, "side": 1})
    assert trade["trade_id"] == 9
    assert trade["price"] == "12.5"
    mark = parse_option_mark(
        {
            "markPrice": "1.2",
            "markIV": "0.55",
            "bidIV": "0.5",
            "askIV": "0.6",
            "delta": "0.4",
            "gamma": "0.01",
            "theta": "-0.02",
            "vega": "0.03",
        }
    )
    assert mark["mark_iv"] == "0.55"
    assert mark["delta"] == "0.4"
    ticker = parse_option_ticker({"lastPrice": "1", "volume": "10", "amount": "20"})
    assert ticker["last_price"] == "1"
    assert ticker["base_volume"] == "10"


def test_parse_option_depth_and_oi():
    depth = parse_option_depth(
        {"bids": [["5", "1"]], "asks": [["6", "2"]], "T": 99, "lastUpdateId": 7}
    )
    assert depth["last_update_id"] == 7
    assert depth["transaction_time"] == 99
    assert depth["bids"] == [["5", "1"]]
    oi = parse_option_open_interest(
        {"symbol": "BTC-260828-65000-C", "sumOpenInterest": "12.5", "timestamp": "1000"}
    )
    assert oi["open_interest"] == "12.5"
    assert oi["observation_time"] == 1000
    assert option_symbol_parts("BTC-260828-65000-C") == ("BTC", "260828")


def test_resolve_source_type_infers_ws_and_rest():
    ws = Envelope(
        product="SPOT",
        stream_name="x@trade",
        source_endpoint="wss://stream.binance.com:9443",
        kind="trade",
        payload={},
    )
    rest = Envelope(
        product="OPTIONS",
        stream_name="rest_depth",
        source_endpoint="https://eapi.binance.com/eapi/v1/depth",
        kind="depth_snapshot",
        payload={},
    )
    backfill = Envelope(
        product="SPOT",
        stream_name="rest_trades",
        source_endpoint="https://api.binance.com/api/v3/aggTrades",
        kind="agg_trade",
        payload={},
        source_type="rest_backfill",
    )
    assert resolve_source_type(ws) == "websocket"
    assert resolve_source_type(rest) == "rest_poll"
    assert resolve_source_type(backfill) == "rest_backfill"


async def test_write_exchange_status_and_options_tables(tmp_path):
    conn = await open_db(str(tmp_path / "opt.db"))
    envs = [
        Envelope(
            product="EXCHANGE",
            stream_name="systemStatus",
            source_endpoint="https://api.binance.com/sapi/v1/system/status",
            kind="exchange_status",
            payload={"status": 0, "msg": "normal", "raw": {"status": 0, "msg": "normal"}},
        ),
        Envelope(
            product="OPTIONS",
            stream_name="rest_mark",
            source_endpoint="https://eapi.binance.com/eapi/v1/mark",
            kind="options_mark",
            payload={
                "mark_price": "1.1",
                "mark_iv": "0.5",
                "bid_iv": "0.4",
                "ask_iv": "0.6",
                "delta": "0.3",
                "gamma": "0.01",
                "theta": "-0.1",
                "vega": "0.2",
                "raw": {"markPrice": "1.1"},
            },
            symbol="BTC-260828-65000-C",
        ),
        Envelope(
            product="OPTIONS",
            stream_name="rest_index",
            source_endpoint="https://eapi.binance.com/eapi/v1/index",
            kind="options_index",
            payload={
                "underlying": "BTCUSDT",
                "index_price": "65000.12",
                "observation_time": 123,
                "raw": {"indexPrice": "65000.12"},
            },
            symbol="BTCUSDT",
        ),
        Envelope(
            product="OPTIONS",
            stream_name="rest_depth",
            source_endpoint="https://eapi.binance.com/eapi/v1/depth",
            kind="depth_snapshot",
            payload={
                "last_update_id": 42,
                "bids": [["1", "2"]],
                "asks": [["3", "4"]],
                "transaction_time": 55,
            },
            symbol="BTC-260828-65000-C",
        ),
        Envelope(
            product="OPTIONS",
            stream_name="rest_openInterest",
            source_endpoint="https://eapi.binance.com/eapi/v1/openInterest",
            kind="open_interest",
            payload={"open_interest": "10.5", "observation_time": 999},
            symbol="BTC-260828-65000-C",
        ),
        Envelope(
            product="SPOT",
            stream_name="btcusdt@trade",
            source_endpoint="wss://stream.binance.com:9443",
            kind="trade",
            payload={
                "trade_id": 1,
                "trade_time": 1,
                "price": "1",
                "quantity": "1",
                "buyer_maker": False,
            },
            symbol="BTCUSDT",
        ),
    ]
    await _write_all(conn, envs)

    cur = await conn.execute("SELECT status_code, msg FROM exchange_status")
    assert await cur.fetchone() == (0, "normal")

    cur = await conn.execute(
        "SELECT symbol, mark_price, mark_iv, typeof(mark_price), typeof(delta) FROM options_mark"
    )
    row = await cur.fetchone()
    assert row[0] == "BTC-260828-65000-C"
    assert row[1] == "1.1"
    assert row[2] == "0.5"
    assert row[3] == "text"
    assert row[4] == "text"

    cur = await conn.execute("SELECT underlying, index_price, typeof(index_price) FROM options_index")
    row = await cur.fetchone()
    assert row == ("BTCUSDT", "65000.12", "text")

    cur = await conn.execute(
        "SELECT last_update_id, transaction_time FROM depth_snapshots WHERE product='OPTIONS'"
    )
    assert await cur.fetchone() == (42, 55)

    cur = await conn.execute(
        "SELECT open_interest, observation_time, typeof(open_interest) FROM open_interest WHERE product='OPTIONS'"
    )
    assert await cur.fetchone() == ("10.5", 999, "text")

    cur = await conn.execute("SELECT source_type, COUNT(*) FROM raw_events GROUP BY source_type ORDER BY 1")
    by_type = {r[0]: r[1] for r in await cur.fetchall()}
    assert by_type["rest_poll"] >= 4
    assert by_type["websocket"] == 1
    await conn.close()
