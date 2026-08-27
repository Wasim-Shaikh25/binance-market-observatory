"""Declared feed inventory: what Binance exposes publicly vs what this
collector implements. Public-availability flags are based on Binance's
long-documented public REST/WS surfaces (no API key). They are not a live
docs scrape — re-verify against official docs if Binance changes the surface.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import Settings


@dataclass(frozen=True)
class FeedSpec:
    product: str  # SPOT | USDM_FUTURES | COINM_FUTURES | OPTIONS | MARGIN
    data_type: str
    publicly_available: bool
    implemented: bool
    notes: str = ""


# Product tags match Envelope.product / DB `product` column.
FEEDS: list[FeedSpec] = [
    # Spot
    FeedSpec("SPOT", "instruments", True, True),
    FeedSpec("SPOT", "trades", True, True),
    FeedSpec("SPOT", "agg_trades", True, True),
    FeedSpec("SPOT", "book_ticker", True, True, "No Binance event timestamp on this stream"),
    FeedSpec("SPOT", "depth", True, True, "Top-N / rotating; not all symbols"),
    FeedSpec("SPOT", "candles", True, True, "Intervals from config only"),
    FeedSpec("SPOT", "ticker_24h", True, True),
    # Margin is metadata on Spot instruments, not a separate market pipeline
    FeedSpec("MARGIN", "metadata", True, True, "margin_tradable on Spot instrument_snapshots"),
    # USDS-M
    FeedSpec("USDM_FUTURES", "instruments", True, True),
    FeedSpec("USDM_FUTURES", "trades", True, True),
    FeedSpec("USDM_FUTURES", "agg_trades", True, True),
    FeedSpec("USDM_FUTURES", "book_ticker", True, True, "No Binance event timestamp"),
    FeedSpec("USDM_FUTURES", "depth", True, True, "Top-N"),
    FeedSpec("USDM_FUTURES", "candles", True, True),
    FeedSpec("USDM_FUTURES", "ticker_24h", True, True),
    FeedSpec("USDM_FUTURES", "mark_price", True, True, "Includes index + estimated funding fields"),
    FeedSpec("USDM_FUTURES", "funding", True, True, "From markPrice stream = estimated/current, not settled history"),
    FeedSpec("USDM_FUTURES", "open_interest", True, True),
    FeedSpec("USDM_FUTURES", "liquidations", True, True),
    FeedSpec("USDM_FUTURES", "positioning", True, True),
    # COIN-M
    FeedSpec("COINM_FUTURES", "instruments", True, True),
    FeedSpec("COINM_FUTURES", "trades", True, True),
    FeedSpec("COINM_FUTURES", "agg_trades", True, True),
    FeedSpec("COINM_FUTURES", "book_ticker", True, True, "No Binance event timestamp"),
    FeedSpec("COINM_FUTURES", "depth", True, True, "Top-N"),
    FeedSpec("COINM_FUTURES", "candles", True, True),
    FeedSpec("COINM_FUTURES", "ticker_24h", True, True),
    FeedSpec("COINM_FUTURES", "mark_price", True, True),
    FeedSpec("COINM_FUTURES", "funding", True, True, "Estimated/current from markPrice"),
    FeedSpec("COINM_FUTURES", "open_interest", True, True),
    FeedSpec("COINM_FUTURES", "liquidations", True, True),
    FeedSpec("COINM_FUTURES", "positioning", True, True, "Uses pair=; takerBuySellVol not takerlongshortRatio"),
    # Options — REST primary (instruments/trades/ticker/mark+IV/index/depth/OI); WS best-effort
    FeedSpec("OPTIONS", "instruments", True, True, "exchangeInfo → instruments + snapshots"),
    FeedSpec("OPTIONS", "trades", True, True, "REST /eapi/v1/trades; WS best-effort"),
    FeedSpec("OPTIONS", "book", True, True, "REST /eapi/v1/depth → depth_snapshots (poll, not WS sync)"),
    FeedSpec("OPTIONS", "ticker", True, True, "REST /eapi/v1/ticker → ticker_24h"),
    FeedSpec("OPTIONS", "open_interest", True, True, "REST /eapi/v1/openInterest → open_interest"),
    FeedSpec("OPTIONS", "iv_greeks", True, True, "REST /eapi/v1/mark → options_mark (IV+greeks as text)"),
    # Cross-cutting / exchange-wide
    FeedSpec("EXCHANGE", "system_status", True, True, "Public /sapi/v1/system/status → exchange_status"),
    FeedSpec("EXCHANGE", "announcements", False, False, "No stable public machine-readable feed in scope"),
    FeedSpec(
        "EXCHANGE",
        "rest_backfill_provenance",
        True,
        True,
        "raw_events.source_type = websocket|rest_poll|rest_backfill; gap_fill crawler for agg_trades/klines",
    ),
]


PRODUCT_CONFIG_KEY = {
    "SPOT": "spot",
    "USDM_FUTURES": "usdm_futures",
    "COINM_FUTURES": "coinm_futures",
    "OPTIONS": "options",
    "MARGIN": "spot",  # folded into spot
}


def product_enabled(settings: Settings, product: str) -> bool:
    key = PRODUCT_CONFIG_KEY.get(product)
    if key is None:
        return False
    cfg = settings.products.get(key)
    return bool(cfg and cfg.enabled)
