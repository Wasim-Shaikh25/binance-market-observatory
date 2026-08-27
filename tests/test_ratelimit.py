import asyncio
import time

import pytest

from src.ratelimit import RestWeightLimiter, WsConnectionLimiter, chunk_symbols


async def test_acquire_within_budget_does_not_block():
    limiter = RestWeightLimiter(capacity_per_minute=100, safety_margin=1.0)
    start = time.monotonic()
    await limiter.acquire(50)
    await limiter.acquire(50)
    assert time.monotonic() - start < 1.0


async def test_acquire_over_budget_waits_for_window_reset():
    limiter = RestWeightLimiter(capacity_per_minute=10, safety_margin=1.0)
    # Shrink the window artificially so the test doesn't take 60s.
    limiter._window_start = time.monotonic() - 59.9
    await limiter.acquire(10)  # exhausts the budget just before reset
    start = time.monotonic()
    await limiter.acquire(5)  # must wait for the window to roll over
    assert time.monotonic() - start >= 0.05


async def test_reconcile_trusts_server_reported_usage():
    limiter = RestWeightLimiter(capacity_per_minute=100, safety_margin=1.0)
    await limiter.acquire(10)
    await limiter.reconcile(90)
    assert limiter._used == 90
    # Local count should never override a higher server-reported value downward.
    await limiter.reconcile(50)
    assert limiter._used == 90


async def test_penalize_blocks_subsequent_acquire():
    limiter = RestWeightLimiter(capacity_per_minute=1000, safety_margin=1.0)
    await limiter.penalize(0.2, reason="test")
    start = time.monotonic()
    await limiter.acquire(1)
    assert time.monotonic() - start >= 0.15


async def test_ws_connection_limiter_throttles_bursts():
    limiter = WsConnectionLimiter(max_connections=2, window_seconds=0.3)
    start = time.monotonic()
    await limiter.acquire()
    await limiter.acquire()
    await limiter.acquire()  # third attempt must wait out the window
    assert time.monotonic() - start >= 0.25


def test_chunk_symbols_splits_evenly():
    symbols = [f"s{i}" for i in range(10)]
    chunks = chunk_symbols(symbols, max_per_connection=4)
    assert chunks == [symbols[0:4], symbols[4:8], symbols[8:10]]
