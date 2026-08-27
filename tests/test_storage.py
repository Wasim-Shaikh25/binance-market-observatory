import asyncio
import json

import pytest

from src.models import Envelope
from src.storage import DBWriter, open_db


async def _write_all(conn, envelopes):
    queue: asyncio.Queue = asyncio.Queue()
    writer = DBWriter(conn, queue)
    task = asyncio.create_task(writer.run())
    for env in envelopes:
        await queue.put(env)
    await queue.put(None)
    await task


async def test_raw_event_always_written_regardless_of_kind(tmp_path):
    conn = await open_db(str(tmp_path / "test.db"))
    env = Envelope(product="SPOT", stream_name="btcusdt@trade", source_endpoint="ws", kind="trade",
                    payload={"trade_id": 1, "trade_time": 111, "price": "10.00", "quantity": "1.00", "buyer_maker": False},
                    symbol="BTCUSDT")
    await _write_all(conn, [env])
    cur = await conn.execute("SELECT product, symbol, stream_name, payload_json FROM raw_events")
    row = await cur.fetchone()
    assert row[0] == "SPOT"
    assert row[1] == "BTCUSDT"
    assert json.loads(row[3])["trade_id"] == 1
    await conn.close()


async def test_trade_side_and_decimal_as_text(tmp_path):
    conn = await open_db(str(tmp_path / "test.db"))
    env = Envelope(product="SPOT", stream_name="btcusdt@trade", source_endpoint="ws", kind="trade",
                    payload={"trade_id": 42, "trade_time": 111, "price": "10000.50000000",
                              "quantity": "0.00300000", "quote_quantity": "30.001500000000000",
                              "buyer_maker": True},
                    symbol="BTCUSDT")
    await _write_all(conn, [env])
    cur = await conn.execute("SELECT price, quantity, buyer_maker, taker_side, typeof(price), typeof(quantity) FROM trades")
    row = await cur.fetchone()
    assert row[0] == "10000.50000000"
    assert row[1] == "0.00300000"
    assert row[2] == 1
    assert row[3] == "SELL"  # buyer was maker -> taker sold
    assert row[4] == "text"
    assert row[5] == "text"
    await conn.close()


async def test_duplicate_trade_id_is_ignored_not_duplicated(tmp_path):
    conn = await open_db(str(tmp_path / "test.db"))
    payload = {"trade_id": 7, "trade_time": 1, "price": "1", "quantity": "1", "buyer_maker": False}
    env = Envelope(product="SPOT", stream_name="btcusdt@trade", source_endpoint="ws", kind="trade", payload=payload, symbol="BTCUSDT")
    await _write_all(conn, [env, env])  # same trade delivered twice (e.g. reconnect replay)
    cur = await conn.execute("SELECT COUNT(*) FROM trades")
    assert (await cur.fetchone())[0] == 1
    cur = await conn.execute("SELECT COUNT(*) FROM raw_events")
    assert (await cur.fetchone())[0] == 2  # raw fidelity: both deliveries preserved
    await conn.close()


async def test_instrument_snapshot_creates_instrument_and_history_row(tmp_path):
    conn = await open_db(str(tmp_path / "test.db"))
    env = Envelope(product="SPOT", stream_name="exchangeInfo", source_endpoint="rest", kind="instrument_snapshot",
                    payload={"status": "TRADING", "base_asset": "BTC", "quote_asset": "USDT",
                              "tick_size": "0.01", "step_size": "0.0001", "min_qty": "0.0001",
                              "min_notional": "5", "margin_tradable": True},
                    symbol="BTCUSDT")
    await _write_all(conn, [env])
    cur = await conn.execute("SELECT exchange, product, symbol FROM instruments")
    inst = await cur.fetchone()
    assert inst == ("binance", "SPOT", "BTCUSDT")
    cur = await conn.execute("SELECT margin_tradable, tick_size FROM instrument_snapshots")
    snap = await cur.fetchone()
    assert snap[0] == 1
    assert snap[1] == "0.01"
    await conn.close()


async def test_two_instrument_snapshots_over_time_both_kept(tmp_path):
    conn = await open_db(str(tmp_path / "test.db"))
    base_payload = {"status": "TRADING", "base_asset": "BTC", "quote_asset": "USDT", "margin_tradable": False}
    env1 = Envelope(product="SPOT", stream_name="exchangeInfo", source_endpoint="rest", kind="instrument_snapshot",
                     payload=base_payload, symbol="BTCUSDT")
    env2 = Envelope(product="SPOT", stream_name="exchangeInfo", source_endpoint="rest", kind="instrument_snapshot",
                     payload={**base_payload, "margin_tradable": True}, symbol="BTCUSDT")
    await _write_all(conn, [env1, env2])
    cur = await conn.execute("SELECT COUNT(*) FROM instruments")
    assert (await cur.fetchone())[0] == 1  # identity is stable
    cur = await conn.execute("SELECT COUNT(*) FROM instrument_snapshots")
    assert (await cur.fetchone())[0] == 2  # history of both states preserved
    await conn.close()


async def test_different_products_are_identifiable_for_same_symbol(tmp_path):
    conn = await open_db(str(tmp_path / "test.db"))
    envs = [
        Envelope(product="SPOT", stream_name="btcusdt@trade", source_endpoint="ws", kind="trade",
                  payload={"trade_id": 1, "trade_time": 1, "price": "1", "quantity": "1", "buyer_maker": False}, symbol="BTCUSDT"),
        Envelope(product="USDM_FUTURES", stream_name="btcusdt@trade", source_endpoint="ws", kind="trade",
                  payload={"trade_id": 1, "trade_time": 1, "price": "1", "quantity": "1", "buyer_maker": False}, symbol="BTCUSDT"),
    ]
    await _write_all(conn, envs)
    cur = await conn.execute("SELECT product FROM trades WHERE symbol='BTCUSDT' ORDER BY product")
    products = [r[0] for r in await cur.fetchall()]
    assert products == ["SPOT", "USDM_FUTURES"]
    await conn.close()


async def test_liquidation_and_funding_rows(tmp_path):
    conn = await open_db(str(tmp_path / "test.db"))
    envs = [
        Envelope(product="USDM_FUTURES", stream_name="!forceOrder@arr", source_endpoint="ws", kind="liquidation",
                  payload={"side": "SELL", "price": "49000", "quantity": "2.0", "order_status": "FILLED"}, symbol="BTCUSDT"),
        Envelope(product="USDM_FUTURES", stream_name="btcusdt@markPrice@1s", source_endpoint="ws", kind="funding_rate",
                  payload={"funding_rate": "0.0001", "funding_time": 123, "mark_price": "50000"}, symbol="BTCUSDT"),
    ]
    await _write_all(conn, envs)
    cur = await conn.execute("SELECT side, price, quantity FROM liquidations")
    assert await cur.fetchone() == ("SELL", "49000", "2.0")
    cur = await conn.execute("SELECT funding_rate, funding_time FROM funding_rate")
    assert await cur.fetchone() == ("0.0001", 123)
    await conn.close()


async def test_unknown_kind_stores_raw_only(tmp_path):
    conn = await open_db(str(tmp_path / "test.db"))
    env = Envelope(product="OPTIONS", stream_name="x@trade", source_endpoint="ws", kind="options_trade",
                    payload={"whatever": "shape"}, symbol="X")
    await _write_all(conn, [env])
    cur = await conn.execute("SELECT COUNT(*) FROM raw_events")
    assert (await cur.fetchone())[0] == 1
    await conn.close()
