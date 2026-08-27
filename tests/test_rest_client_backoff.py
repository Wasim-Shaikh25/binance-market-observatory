"""Proves RestClient actually backs off on Binance's rate-limit responses
(429) and reconciles its weight budget from the exchange's own header,
rather than only doing so in the limiter's isolated unit tests."""

from __future__ import annotations

import time

from aiohttp import ClientSession, web

from src.binance_client import RestClient
from src.ratelimit import RestWeightLimiter


async def test_rest_client_retries_after_429_and_reconciles_weight(aiohttp_unused_port=None):
    calls = {"n": 0}

    async def handler(request: web.Request) -> web.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            resp = web.Response(status=429)
            resp.headers["Retry-After"] = "0.3"
            return resp
        resp = web.json_response({"ok": True})
        resp.headers["X-MBX-USED-WEIGHT-1M"] = "777"
        return resp

    app = web.Application()
    app.router.add_get("/ping", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]

    try:
        async with ClientSession() as session:
            limiter = RestWeightLimiter(capacity_per_minute=1200)
            rest = RestClient(session, f"http://127.0.0.1:{port}", limiter)
            start = time.monotonic()
            data = await rest.get_json("/ping", weight=1)
            elapsed = time.monotonic() - start
    finally:
        await runner.cleanup()

    assert data == {"ok": True}
    assert calls["n"] == 2
    assert elapsed >= 0.25, "expected RestClient to honor Retry-After before retrying"
    assert limiter._used == 777, "expected the limiter to adopt the server-reported used weight"


async def test_rest_client_gives_up_after_persistent_429(aiohttp_unused_port=None):
    async def always_429(request: web.Request) -> web.Response:
        resp = web.Response(status=429)
        resp.headers["Retry-After"] = "0.05"
        return resp

    app = web.Application()
    app.router.add_get("/ping", always_429)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]

    try:
        async with ClientSession() as session:
            rest = RestClient(session, f"http://127.0.0.1:{port}", RestWeightLimiter(1200))
            raised = False
            try:
                await rest.get_json("/ping", weight=1, retries=2)
            except RuntimeError:
                raised = True
            assert raised, "expected RestClient to eventually give up rather than retry forever"
    finally:
        await runner.cleanup()
