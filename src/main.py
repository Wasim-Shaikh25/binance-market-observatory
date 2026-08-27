"""Entrypoint: wires the capability registry to connectors, the internal
queue, and the single DB writer (docs/ARCHITECTURE.md #1-#2).

Usage:
    python -m src.main [--config config/settings.yaml]
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal

import aiohttp

from .config import load_settings
from .connectors import coinm, options, spot, usdm
from .connectors.market import ConnectorContext
from .binance_client import RestClient
from .ratelimit import RestWeightLimiter, WsConnectionLimiter
from .storage import DBWriter, open_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("main")

RUNNERS = {
    "spot": spot.run,
    "usdm_futures": usdm.run,
    "coinm_futures": coinm.run,
    "options": options.run,
}


async def run(config_path: str) -> None:
    settings = load_settings(config_path)
    conn = await open_db(settings.database_path)
    queue: asyncio.Queue = asyncio.Queue(maxsize=10000)
    writer = DBWriter(conn, queue)
    writer_task = asyncio.create_task(writer.run())

    try:
        async with aiohttp.ClientSession(trust_env=True) as session:
            product_tasks = []
            for key, cfg in settings.products.items():
                if not cfg.enabled:
                    logger.info("Product %s disabled in config, skipping", key)
                    continue
                rest_limiter = RestWeightLimiter(cfg.rest_weight_per_minute)
                ws_limiter = WsConnectionLimiter(settings.ws_connections_per_5min)
                rest = RestClient(session, cfg.rest_base_url, rest_limiter)
                ctx = ConnectorContext(
                    queue=queue,
                    session=session,
                    rest=rest,
                    ws_limiter=ws_limiter,
                    db=conn,
                    max_streams_per_connection=settings.max_streams_per_connection,
                )
                runner = RUNNERS[key]
                logger.info("Starting connector: %s", key)
                product_tasks.append(asyncio.create_task(runner(cfg, ctx), name=key))

            stop = asyncio.Event()
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                try:
                    loop.add_signal_handler(sig, stop.set)
                except NotImplementedError:
                    pass  # not available on all platforms

            try:
                await stop.wait()
                logger.info("Shutdown requested, stopping connectors...")
            finally:
                for t in product_tasks:
                    t.cancel()
                await asyncio.gather(*product_tasks, return_exceptions=True)
    finally:
        # Always drain the writer and close the DB cleanly, whether we got
        # here via graceful shutdown (stop.set()) or the run() task itself
        # being cancelled (e.g. a supervising process killing it outright).
        await queue.put(None)  # sentinel to stop the writer
        await writer_task
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/settings.yaml")
    args = parser.parse_args()
    asyncio.run(run(args.config))


if __name__ == "__main__":
    main()
