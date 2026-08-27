from ..config import ProductConfig
from .market import ConnectorContext, ProductPaths, run_market_product

# Positioning paths verified live 2026-08-27: same `/futures/data/<metric>` prefix
# as USDS-M, but the query key is `pair` (e.g. BTCUSD), not contract `symbol`
# (BTCUSD_PERP) -- `symbol=` returns HTTP 400 on dapi.binance.com.
# COIN-M has no `takerlongshortRatio` endpoint (404); the volume analogue is
# `takerBuySellVol` (buy/sell volumes, no ratio field -- value stored as null,
# full payload in payload_json).
COINM_PATHS = ProductPaths(
    exchange_info_path="/dapi/v1/exchangeInfo",
    depth_path="/dapi/v1/depth",
    is_futures=True,
    open_interest_path="/dapi/v1/openInterest",
    force_order_stream="!forceOrder@arr",
    mark_price_suffix="@markPrice@1s",
    positioning_endpoints=(
        "globalLongShortAccountRatio",
        "topLongShortAccountRatio",
        "topLongShortPositionRatio",
        "takerBuySellVol",
    ),
    positioning_query_param="pair",
)


async def run(cfg: ProductConfig, ctx: ConnectorContext) -> None:
    await run_market_product(cfg, ctx, COINM_PATHS)
