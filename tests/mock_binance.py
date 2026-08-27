"""A local, protocol-faithful stand-in for Binance's public REST + combined
WebSocket stream API, used because this sandbox cannot reach the real
Binance servers (see STATUS.md). It reproduces the exact message shapes the
real connectors parse (trade/aggTrade/bookTicker/ticker/kline/depth diffs,
exchangeInfo, depth snapshots, SUBSCRIBE/UNSUBSCRIBE control messages) plus
two deliberately adversarial behaviors so the tests can prove the collector
handles them correctly:

- the first broad-stream connection is force-closed after a few messages,
  to exercise reconnect/backoff.
- the depth stream silently burns one update ID partway through, to
  exercise gap detection and resync.
"""

from __future__ import annotations

import asyncio
import itertools
import json

from aiohttp import WSMsgType, web


def make_app(symbols: tuple[str, ...] = ("BTCUSDT",)) -> web.Application:
    app = web.Application()
    app["symbols"] = symbols
    app["state"] = {
        "depth_counter": {s: 1000 for s in symbols},
        "depth_msgs_sent": {s: 0 for s in symbols},
        "gap_injected": {s: False for s in symbols},
        "broad_connections": 0,
        "used_weight": 10,
        "rest_calls": 0,
    }
    app.router.add_get("/api/v3/exchangeInfo", handle_exchange_info)
    app.router.add_get("/api/v3/depth", handle_depth_snapshot)
    app.router.add_get("/stream", handle_stream)
    return app


async def handle_exchange_info(request: web.Request) -> web.Response:
    app = request.app
    app["state"]["rest_calls"] += 1
    symbols_payload = [
        {
            "symbol": s,
            "status": "TRADING",
            "baseAsset": s[:3],
            "quoteAsset": s[3:],
            "isMarginTradingAllowed": True,
            "filters": [
                {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                {"filterType": "LOT_SIZE", "stepSize": "0.0001", "minQty": "0.0001"},
                {"filterType": "NOTIONAL", "minNotional": "5"},
            ],
        }
        for s in app["symbols"]
    ]
    resp = web.json_response({"symbols": symbols_payload})
    resp.headers["X-MBX-USED-WEIGHT-1M"] = str(app["state"]["used_weight"])
    return resp


async def handle_depth_snapshot(request: web.Request) -> web.Response:
    app = request.app
    symbol = request.query.get("symbol", "").upper()
    counter = app["state"]["depth_counter"].get(symbol, 1000)
    return web.json_response(
        {
            "lastUpdateId": counter,
            "bids": [["100.00", "1.0"], ["99.99", "2.0"]],
            "asks": [["100.01", "1.0"], ["100.02", "2.0"]],
        }
    )


async def handle_stream(request: web.Request) -> web.WebSocketResponse:
    ws = web.WebSocketResponse(heartbeat=5)
    await ws.prepare(request)
    app = request.app
    state = app["state"]

    query_streams = [s for s in request.query.get("streams", "").split("/") if s]
    my_broad_id = None
    if query_streams:
        state["broad_connections"] += 1
        my_broad_id = state["broad_connections"]

    subscribed_depth: set[str] = set()
    trade_ids = itertools.count(1)

    async def broad_sender() -> None:
        i = 0
        while True:
            for stream in query_streams:
                symbol = stream.split("@")[0].upper()
                data = _broad_message(stream, symbol, i, next(trade_ids))
                if data is not None:
                    await ws.send_str(json.dumps({"stream": stream, "data": data}))
            i += 1
            if my_broad_id == 1 and i == 3:
                await ws.close()
                return
            await asyncio.sleep(0.05)

    async def depth_sender() -> None:
        while True:
            await asyncio.sleep(0.05)
            for symbol in list(subscribed_depth):
                counter = state["depth_counter"][symbol]
                sent = state["depth_msgs_sent"][symbol]
                skip = 1 if (sent == 5 and not state["gap_injected"][symbol]) else 0
                if skip:
                    state["gap_injected"][symbol] = True
                update_id = counter + 1 + skip
                state["depth_counter"][symbol] = update_id
                state["depth_msgs_sent"][symbol] = sent + 1
                payload = {"U": update_id, "u": update_id, "b": [["100.00", "1.5"]], "a": [["100.01", "1.5"]], "E": 1}
                await ws.send_str(json.dumps({"stream": f"{symbol.lower()}@depth@100ms", "data": payload}))

    tasks = [asyncio.create_task(broad_sender()), asyncio.create_task(depth_sender())]
    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    control = json.loads(msg.data)
                except json.JSONDecodeError:
                    continue
                method = control.get("method")
                params = control.get("params", [])
                if method == "SUBSCRIBE":
                    subscribed_depth.update(p.split("@")[0].upper() for p in params if "@depth" in p)
                    await ws.send_str(json.dumps({"result": None, "id": control.get("id")}))
                elif method == "UNSUBSCRIBE":
                    for p in params:
                        if "@depth" in p:
                            subscribed_depth.discard(p.split("@")[0].upper())
                    await ws.send_str(json.dumps({"result": None, "id": control.get("id")}))
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    return ws


def _broad_message(stream: str, symbol: str, i: int, trade_id: int) -> dict | None:
    if stream.endswith("@trade"):
        return {"e": "trade", "E": 1, "s": symbol, "t": trade_id, "T": 1, "p": "100.00", "q": "0.01", "m": i % 2 == 0}
    if stream.endswith("@aggTrade"):
        return {"e": "aggTrade", "E": 1, "s": symbol, "a": trade_id, "p": "100.00", "q": "0.01", "T": 1, "m": False}
    if stream.endswith("@bookTicker"):
        return {"u": i, "s": symbol, "b": "99.99", "B": "1.0", "a": "100.01", "A": "1.0"}
    if stream.endswith("@ticker"):
        return {
            "e": "24hrTicker", "s": symbol, "p": "1", "P": "1", "w": "100", "c": "100", "o": "99", "h": "101",
            "l": "98", "v": "1000", "q": "100000", "O": 1, "C": 2, "F": 1, "L": 2, "n": 2,
        }
    if "@kline_" in stream:
        interval = stream.split("_", 1)[1]
        return {
            "e": "kline", "s": symbol,
            "k": {"t": 1, "T": 2, "i": interval, "o": "1", "h": "2", "l": "1", "c": "1.5", "v": "10",
                  "n": 5, "x": (i % 3 == 0), "q": "15", "V": "5", "Q": "7.5"},
        }
    return None
