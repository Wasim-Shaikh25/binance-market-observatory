"""Binance rate-limit compliance.

Binance enforces two independent limit systems relevant to a public-data-only
collector:

1. REST "request weight" -- a rolling per-minute budget per IP, reported back
   on every response via an `X-MBX-USED-WEIGHT-1M`-style header (the exact
   header name varies slightly per product: `X-MBX-USED-WEIGHT-1M` on Spot,
   similar on USDS-M/COIN-M futures). Exceeding it returns HTTP 429; ignoring
   429s and continuing gets the IP banned with HTTP 418.
2. WebSocket connection churn -- a cap on new connection attempts within a
   rolling window per IP, a cap on streams per connection, and a ~24h forced
   disconnect per connection.

The exact numeric limits are Binance's own documented values and do change
over time (see docs/THESIS.md #7 -- capability registry philosophy: fix
drift here in config, not by hard-coding assumptions through the codebase).
The defaults below are deliberately conservative fractions of Binance's
long-documented public defaults; `RestWeightLimiter.reconcile` corrects for
drift automatically using the server's own reported usage, which is what
actually prevents a ban regardless of whether the configured default is
still current.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque

logger = logging.getLogger(__name__)

# Conservative defaults, deliberately under Binance's documented public
# maximums, re-verify against current Binance docs before raising these.
DEFAULT_REST_WEIGHT_PER_MINUTE = 1200
DEFAULT_WS_CONNECTIONS_PER_5MIN = 150
DEFAULT_MAX_STREAMS_PER_CONNECTION = 100
DEFAULT_WS_RECONNECT_BEFORE_SECONDS = 23 * 3600  # reconnect proactively before Binance's ~24h cutoff


class RestWeightLimiter:
    """Token-bucket limiter over a rolling 1-minute window, self-correcting
    against the exchange's own reported used-weight header."""

    def __init__(self, capacity_per_minute: int = DEFAULT_REST_WEIGHT_PER_MINUTE, safety_margin: float = 0.85):
        self.budget = max(1, int(capacity_per_minute * safety_margin))
        self._used = 0
        self._window_start = time.monotonic()
        self._lock = asyncio.Lock()
        self._penalized_until = 0.0

    async def acquire(self, weight: int) -> None:
        while True:
            async with self._lock:
                now = time.monotonic()
                if now < self._penalized_until:
                    wait = self._penalized_until - now
                else:
                    if now - self._window_start >= 60:
                        self._window_start = now
                        self._used = 0
                    if self._used + weight <= self.budget:
                        self._used += weight
                        return
                    wait = max(0.0, 60 - (now - self._window_start))
            await asyncio.sleep(min(wait, 5) if wait > 0 else 0.05)

    async def reconcile(self, server_used_weight: int | None) -> None:
        """Trust the server's own counter over our local estimate -- it sees
        all traffic from this IP, not just what this process issued."""
        if server_used_weight is None:
            return
        async with self._lock:
            self._used = max(self._used, server_used_weight)

    async def penalize(self, retry_after_seconds: float, reason: str = "429") -> None:
        async with self._lock:
            self._penalized_until = max(self._penalized_until, time.monotonic() + retry_after_seconds)
        logger.warning("Rate limit backoff (%s): sleeping %.1fs", reason, retry_after_seconds)


class WsConnectionLimiter:
    """Caps new WebSocket connection attempts within a rolling window so a
    burst of reconnects (e.g. many symbols resyncing at once) can't itself
    trip Binance's connection-attempt limit."""

    def __init__(
        self,
        max_connections: int = DEFAULT_WS_CONNECTIONS_PER_5MIN,
        window_seconds: float = 300.0,
    ):
        self._max = max_connections
        self._window = window_seconds
        self._attempts: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        while True:
            async with self._lock:
                now = time.monotonic()
                while self._attempts and now - self._attempts[0] > self._window:
                    self._attempts.popleft()
                if len(self._attempts) < self._max:
                    self._attempts.append(now)
                    return
                wait = self._window - (now - self._attempts[0])
            await asyncio.sleep(max(wait, 0.05))


def chunk_symbols(symbols: list[str], max_per_connection: int = DEFAULT_MAX_STREAMS_PER_CONNECTION) -> list[list[str]]:
    """Split a symbol list into groups that fit under the per-connection
    stream cap, so one connection never has to subscribe to everything."""
    return [symbols[i : i + max_per_connection] for i in range(0, len(symbols), max_per_connection)]
