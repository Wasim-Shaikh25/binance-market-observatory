"""Capability registry / settings loader.

Binance's API surface changes over time and differs per product; per
docs/THESIS.md #7 this project keeps that variability in config, not
scattered through connector code. Adding a product, changing which symbols
get full depth tracking, or adjusting rate-limit budgets should be a config
edit here, not a code change.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import yaml

PRODUCT_TAGS = {
    "spot": "SPOT",
    "usdm_futures": "USDM_FUTURES",
    "coinm_futures": "COINM_FUTURES",
    "options": "OPTIONS",
}


@dataclass
class DepthConfig:
    enabled: bool = True
    mode: str = "top_n"
    top_n: int = 50
    ranking: str = "quote_volume"
    refresh_minutes: int = 15


@dataclass
class ProductConfig:
    key: str
    tag: str
    enabled: bool
    rest_base_url: str
    ws_base_url: str
    rest_weight_per_minute: int = 1200
    symbol_universe: str = "all"  # "all" | "list"
    symbol_list: list[str] = field(default_factory=list)
    instrument_poll_minutes: int = 60
    kline_intervals: list[str] = field(default_factory=list)
    depth: DepthConfig = field(default_factory=DepthConfig)
    funding_poll_minutes: int | None = None
    open_interest_poll_minutes: int | None = None


@dataclass
class Settings:
    database_path: str
    products: dict[str, ProductConfig]
    ws_connections_per_5min: int = 150
    max_streams_per_connection: int = 100


def load_settings(path: str) -> Settings:
    with open(path) as f:
        raw = yaml.safe_load(f)

    products: dict[str, ProductConfig] = {}
    for key, p in raw.get("products", {}).items():
        if key not in PRODUCT_TAGS:
            raise ValueError(f"Unknown product key in registry: {key}")
        depth_raw = p.get("depth") or {}
        products[key] = ProductConfig(
            key=key,
            tag=PRODUCT_TAGS[key],
            enabled=bool(p.get("enabled", False)),
            rest_base_url=p["rest_base_url"],
            ws_base_url=p["ws_base_url"],
            rest_weight_per_minute=int(p.get("rest_weight_per_minute", 1200)),
            symbol_universe=p.get("symbol_universe", "all"),
            symbol_list=list(p.get("symbol_list", [])),
            instrument_poll_minutes=int(p.get("instrument_poll_minutes", 60)),
            kline_intervals=list(p.get("kline_intervals", [])),
            depth=DepthConfig(**depth_raw),
            funding_poll_minutes=p.get("funding_poll_minutes"),
            open_interest_poll_minutes=p.get("open_interest_poll_minutes"),
        )

    rl = raw.get("rate_limits", {})
    return Settings(
        database_path=raw["database"]["path"],
        products=products,
        ws_connections_per_5min=int(rl.get("ws_connections_per_5min", 150)),
        max_streams_per_connection=int(rl.get("max_streams_per_connection", 100)),
    )
