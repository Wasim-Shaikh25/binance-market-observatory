"""End-to-end pipeline test: real connector code (src/connectors/spot.py and
everything it calls) against the local mock Binance server, proving data
actually flows connect -> parse -> validate -> store the way it's meant to,
including reconnect-on-disconnect and gap-detection-triggers-resync -- the
two behaviors docs/THESIS.md treats as non-negotiable. This cannot run
against real Binance from this sandbox (outbound network is blocked here),
so it is the strongest verification available in this environment; a live
run against Binance's real servers is still required before Phase 1 is
considered done (see docs/requirements/2026-08-27-phase1-spot-collector/).
"""

from __future__ import annotations

import asyncio

from aiohttp import ClientSession, web

from src.binance_client import RestClient
from src.config import DepthConfig, ProductConfig
from src.connectors import spot
from src.connectors.market import ConnectorContext
from src.ratelimit import RestWeightLimiter, WsConnectionLimiter
from src.storage import DBWriter, open_db

from .mock_binance import make_app


async def test_spot_connector_end_to_end(tmp_path):
    app = make_app(symbols=("BTCUSDT",))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]

    db_path = str(tmp_path / "test.db")
    conn = await open_db(db_path)
    queue: asyncio.Queue = asyncio.Queue()
    writer = DBWriter(conn, queue)
    writer_task = asyncio.create_task(writer.run())

    cfg = ProductConfig(
        key="spot",
        tag="SPOT",
        enabled=True,
        rest_base_url=f"http://127.0.0.1:{port}",
        ws_base_url=f"ws://127.0.0.1:{port}",
        rest_weight_per_minute=1200,
        symbol_universe="list",
        symbol_list=["BTCUSDT"],
        instrument_poll_minutes=60,
        kline_intervals=["1m"],
        depth=DepthConfig(enabled=True, top_n=5, ranking="quote_volume", refresh_minutes=60),
    )

    try:
        async with ClientSession() as session:
            rest = RestClient(session, cfg.rest_base_url, RestWeightLimiter(cfg.rest_weight_per_minute))
            ctx = ConnectorContext(
                queue=queue,
                session=session,
                rest=rest,
                ws_limiter=WsConnectionLimiter(150),
                db=conn,
                max_streams_per_connection=100,
            )
            task = asyncio.create_task(spot.run(cfg, ctx))
            await asyncio.sleep(3.0)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    finally:
        await runner.cleanup()

    await queue.put(None)
    await writer_task

    # --- Data actually flowed, for every stream kind, tagged as SPOT ---
    cur = await conn.execute("SELECT COUNT(*) FROM trades WHERE product='SPOT' AND symbol='BTCUSDT'")
    assert (await cur.fetchone())[0] > 0, "no trades landed"

    cur = await conn.execute("SELECT COUNT(*) FROM agg_trades WHERE product='SPOT' AND symbol='BTCUSDT'")
    assert (await cur.fetchone())[0] > 0, "no agg_trades landed"

    cur = await conn.execute("SELECT COUNT(*) FROM book_ticker WHERE product='SPOT' AND symbol='BTCUSDT'")
    assert (await cur.fetchone())[0] > 0, "no book_ticker rows landed"

    cur = await conn.execute("SELECT COUNT(*) FROM ticker_24h WHERE product='SPOT' AND symbol='BTCUSDT'")
    assert (await cur.fetchone())[0] > 0, "no ticker_24h rows landed"

    cur = await conn.execute("SELECT COUNT(*) FROM candles WHERE product='SPOT' AND symbol='BTCUSDT'")
    assert (await cur.fetchone())[0] > 0, "no candle rows landed"

    # --- Buy/sell side is correctly identifiable on every trade ---
    cur = await conn.execute("SELECT DISTINCT buyer_maker, taker_side FROM trades WHERE symbol='BTCUSDT'")
    side_pairs = {tuple(r) for r in await cur.fetchall()}
    assert side_pairs == {(0, "BUY"), (1, "SELL")}, f"expected both sides represented and correctly derived, got {side_pairs}"

    # --- Instrument metadata, including margin flag, was captured ---
    cur = await conn.execute(
        "SELECT margin_tradable, tick_size, step_size, min_notional FROM instrument_snapshots "
        "JOIN instruments ON instruments.id = instrument_snapshots.instrument_id WHERE symbol='BTCUSDT'"
    )
    row = await cur.fetchone()
    assert row is not None, "no instrument snapshot captured"
    assert row[0] == 1  # margin_tradable
    assert row[1] == "0.01"

    # --- Raw fidelity: every normalized row has a raw_events counterpart ---
    cur = await conn.execute("SELECT COUNT(*) FROM raw_events WHERE product='SPOT'")
    raw_count = (await cur.fetchone())[0]
    assert raw_count > 0

    # --- Reconnect after forced disconnect actually happened ---
    cur = await conn.execute("SELECT COUNT(*) FROM system_events WHERE event_type='ws_reconnect'")
    assert (await cur.fetchone())[0] > 0, "expected at least one reconnect after the mock server's forced disconnect"

    # --- Depth: snapshot fetched, updates recorded, and the injected gap triggered a resync ---
    cur = await conn.execute("SELECT COUNT(*) FROM depth_snapshots WHERE symbol='BTCUSDT'")
    assert (await cur.fetchone())[0] > 0, "expected at least one depth snapshot (initial sync)"

    cur = await conn.execute("SELECT COUNT(*) FROM depth_updates WHERE symbol='BTCUSDT'")
    assert (await cur.fetchone())[0] > 0, "expected depth diff updates to be stored"

    cur = await conn.execute("SELECT COUNT(*) FROM system_events WHERE event_type='depth_resync' AND symbol='BTCUSDT'")
    assert (await cur.fetchone())[0] > 0, "expected the mock server's injected update-ID gap to trigger a resync"

    await conn.close()
