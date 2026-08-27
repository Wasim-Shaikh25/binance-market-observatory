"""Shared envelope contract between connectors and the DB writer.

Every connector, regardless of product, emits Envelope instances into the
internal queue. This is the one coupling point between connectors and
storage (see docs/ARCHITECTURE.md #1) -- connectors never touch the database
directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def taker_side(buyer_is_maker: bool) -> str:
    """Binance's `m`/isBuyerMaker flag tells us who was the maker; the taker
    (the side that crossed the spread and is usually the more interesting
    side for behavioral research) is the opposite party."""
    return "SELL" if buyer_is_maker else "BUY"


@dataclass
class Envelope:
    product: str  # SPOT | USDM_FUTURES | COINM_FUTURES | OPTIONS
    stream_name: str  # exact Binance stream/endpoint identifier, e.g. "btcusdt@trade"
    source_endpoint: str  # base URL or REST path the payload came from
    kind: str  # routes to a normalized-table writer, e.g. "trade", "depth_update"
    payload: dict[str, Any]  # near-raw Binance payload, preserved in raw_events
    symbol: Optional[str] = None
    schema_version: str = "1"
    observed_at: str = field(default_factory=now_iso)
    # websocket | rest_poll | rest_backfill. If None, inferred from source_endpoint.
    source_type: Optional[str] = None


def resolve_source_type(env: Envelope) -> str:
    if env.source_type:
        return env.source_type
    ep = (env.source_endpoint or "").lower()
    if ep == "internal" or ep.startswith("internal:"):
        return "internal"
    if ep.startswith("wss:") or ep.startswith("ws:"):
        return "websocket"
    if ep.startswith("http://") or ep.startswith("https://"):
        return "rest_poll"
    return "unknown"
