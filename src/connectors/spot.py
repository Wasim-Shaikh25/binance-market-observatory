from ..config import ProductConfig
from .market import ConnectorContext, ProductPaths, run_market_product

SPOT_PATHS = ProductPaths(
    exchange_info_path="/api/v3/exchangeInfo",
    depth_path="/api/v3/depth",
    is_futures=False,
)


async def run(cfg: ProductConfig, ctx: ConnectorContext) -> None:
    await run_market_product(cfg, ctx, SPOT_PATHS)
