from ..config import ProductConfig
from .market import ConnectorContext, ProductPaths, run_market_product

COINM_PATHS = ProductPaths(
    exchange_info_path="/dapi/v1/exchangeInfo",
    depth_path="/dapi/v1/depth",
    is_futures=True,
    open_interest_path="/dapi/v1/openInterest",
    force_order_stream="!forceOrder@arr",
    mark_price_suffix="@markPrice@1s",
)


async def run(cfg: ProductConfig, ctx: ConnectorContext) -> None:
    await run_market_product(cfg, ctx, COINM_PATHS)
