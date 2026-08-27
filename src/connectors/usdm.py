from ..config import ProductConfig
from .market import ConnectorContext, ProductPaths, run_market_product

# Positioning endpoint paths (docs/requirements/2026-08-27-positioning-coverage-tiers-
# and-timestamp-audit/) could not be verified against live Binance docs from this
# sandbox -- confirm before relying on them; a wrong path fails loud as a
# rest_failure system_event rather than silently storing nothing.
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
