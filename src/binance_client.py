"""Low-level HTTP/WebSocket transport, rate-limit-aware.

Connectors never call aiohttp directly -- everything goes through RestClient
or ws_messages() so rate limiting and reconnect/backoff behavior is uniform
across every product.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, AsyncIterator

import aiohttp

from .ratelimit import RestWeightLimiter, WsConnectionLimiter, DEFAULT_WS_RECONNECT_BEFORE_SECONDS

logger = logging.getLogger(__name__)


class RestClient:
    def __init__(
        self,
        session: aiohttp.ClientSession,
        base_url: str,
        limiter: RestWeightLimiter,
        weight_header: str = "X-MBX-USED-WEIGHT-1M",
    ):
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._limiter = limiter
        self._weight_header = weight_header

    async def get_json(self, path: str, weight: int = 1, params: dict | None = None, retries: int = 5) -> Any:
        last_status = None
        for _ in range(retries):
            await self._limiter.acquire(weight)
            async with self._session.get(self._base_url + path, params=params) as resp:
                used = resp.headers.get(self._weight_header)
                if used is not None:
                    try:
                        await self._limiter.reconcile(int(used))
                    except ValueError:
                        pass
                if resp.status == 429:
                    last_status = 429
                    retry_after = float(resp.headers.get("Retry-After", 5))
                    await self._limiter.penalize(retry_after, reason="429-rate-limit")
                    continue
                if resp.status == 418:
                    last_status = 418
                    retry_after = float(resp.headers.get("Retry-After", 120))
                    await self._limiter.penalize(retry_after, reason="418-ip-ban")
                    continue
                resp.raise_for_status()
                return await resp.json()
        raise RuntimeError(f"REST call to {path} failed after {retries} attempts (last status {last_status})")


async def ws_messages(
    session: aiohttp.ClientSession,
    url: str,
    ws_limiter: WsConnectionLimiter,
    reconnect_after_seconds: float = DEFAULT_WS_RECONNECT_BEFORE_SECONDS,
) -> AsyncIterator[tuple[str, Any]]:
    """Yields ('connected', ws) / ('message', dict) / ('disconnected'|'error'|
    'reconnect_scheduled', detail) / ('reconnecting', backoff_seconds) lifecycle
    events. The live `ws` object is handed back on connect so callers that need
    to send control frames (e.g. depth SUBSCRIBE/UNSUBSCRIBE) can do so.
    Reconnects with exponential backoff on any disconnect or error, and
    proactively reconnects before Binance's ~24h forced cutoff.

    Note: aiohttp's WebSocket iterator swallows CLOSE/CLOSING/CLOSED frames
    internally (it raises StopAsyncIteration for them rather than handing them
    to the loop body), so a server-initiated close ends `async for msg in ws`
    silently -- a terminal event is always emitted explicitly below rather
    than relying on seeing one of those message types in the loop body.
    """
    backoff = 1.0
    while True:
        await ws_limiter.acquire()
        connected_at = time.monotonic()
        terminal_emitted = False
        try:
            async with session.ws_connect(url, heartbeat=20) as ws:
                yield ("connected", ws)
                backoff = 1.0
                async for msg in ws:
                    if time.monotonic() - connected_at > reconnect_after_seconds:
                        yield ("reconnect_scheduled", "proactive-24h-cutoff")
                        terminal_emitted = True
                        await ws.close()
                        break
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        try:
                            yield ("message", json.loads(msg.data))
                        except json.JSONDecodeError:
                            yield ("error", f"non-JSON message: {msg.data[:200]}")
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        yield ("disconnected", str(ws.exception()))
                        terminal_emitted = True
                        break
                if not terminal_emitted:
                    yield ("disconnected", "closed")
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as exc:
            yield ("error", str(exc))
        yield ("reconnecting", backoff)
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 60)
