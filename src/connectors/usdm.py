from ..config import ProductConfig
from .market import ConnectorContext, ProductPaths, run_market_product

USDM_PATHS = ProductPaths(
    exchange_info_path="/fapi/v1/exchangeInfo",
    depth_path="/fapi/v1/depth",
    is_futures=True,
    open_interest_path="/fapi/v1/openInterest",
    force_order_stream="!forceOrder@arr",
    mark_price_suffix="@markPrice@1s",
)


async def run(cfg: ProductConfig, ctx: ConnectorContext) -> None:
    await run_market_product(cfg, ctx, USDM_PATHS)
