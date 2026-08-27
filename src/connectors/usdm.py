from ..config import ProductConfig
from .market import ConnectorContext, ProductPaths, run_market_product

# Positioning paths verified live 2026-08-27: `/futures/data/<metric>` with
# `symbol=` (e.g. BTCUSDT) on fapi.binance.com.
# WebSocket base URL must be wss://fstream.binancefuture.com (config) — the
# fstream.binance.com host can silently omit aggTrade/ticker/kline/markPrice/
# forceOrder while still delivering trade+bookTicker.
USDM_PATHS = ProductPaths(
    exchange_info_path="/fapi/v1/exchangeInfo",
    depth_path="/fapi/v1/depth",
    is_futures=True,
    open_interest_path="/fapi/v1/openInterest",
    force_order_stream="!forceOrder@arr",
    mark_price_suffix="@markPrice@1s",
    positioning_endpoints=(
        "globalLongShortAccountRatio",
        "topLongShortAccountRatio",
        "topLongShortPositionRatio",
        "takerlongshortRatio",
    ),
)


async def run(cfg: ProductConfig, ctx: ConnectorContext) -> None:
    await run_market_product(cfg, ctx, USDM_PATHS)
