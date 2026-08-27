"""Smoke-tests the real entrypoint (src/main.py) wiring config -> connectors
-> queue -> writer, and the audit report generator, against the mock
Binance server -- not just the individual connector as test_integration_spot
does."""

from __future__ import annotations

import asyncio

import yaml
from aiohttp import web

from src.config import load_settings
from src.health import generate_audit_report
from src.main import run
from src.storage import open_db

from .mock_binance import make_app


async def test_main_run_wires_config_to_database(tmp_path):
    app = make_app(symbols=("BTCUSDT",))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]

    db_path = tmp_path / "market.db"
    config = {
        "database": {"path": str(db_path)},
        "products": {
            "spot": {
                "enabled": True,
                "rest_base_url": f"http://127.0.0.1:{port}",
                "ws_base_url": f"ws://127.0.0.1:{port}",
                "rest_weight_per_minute": 1200,
                "symbol_universe": "list",
                "symbol_list": ["BTCUSDT"],
                "instrument_poll_minutes": 60,
                "kline_intervals": ["1m"],
                "depth": {"enabled": True, "top_n": 5, "ranking": "quote_volume", "refresh_minutes": 60},
            },
            "usdm_futures": {"enabled": False, "rest_base_url": "https://fapi.binance.com", "ws_base_url": "wss://fstream.binance.com"},
            "coinm_futures": {"enabled": False, "rest_base_url": "https://dapi.binance.com", "ws_base_url": "wss://dstream.binance.com"},
            "options": {"enabled": False, "rest_base_url": "https://eapi.binance.com", "ws_base_url": "wss://nbstream.binance.com/eoptions"},
        },
        "rate_limits": {"ws_connections_per_5min": 150, "max_streams_per_connection": 100},
    }
    config_path = tmp_path / "settings.yaml"
    config_path.write_text(yaml.dump(config))

    try:
        task = asyncio.create_task(run(str(config_path)))
        await asyncio.sleep(2.5)
        task.cancel()
        import contextlib

        with contextlib.suppress(asyncio.CancelledError):
            await task
    finally:
        await runner.cleanup()

    settings = load_settings(str(config_path))
    conn = await open_db(settings.database_path)
    try:
        cur = await conn.execute("SELECT COUNT(*) FROM trades WHERE product='SPOT'")
        assert (await cur.fetchone())[0] > 0, "main.py wiring did not produce any trade rows"

        report = await generate_audit_report(conn, settings.database_path)
        assert "# Collector Audit Report" in report
        assert "SPOT" in report
        assert "Symbol coverage" in report
        assert "Depth resyncs" in report
    finally:
        await conn.close()
