"""Entrypoint: wires the capability registry to connectors, the internal
queue, and the single DB writer (docs/ARCHITECTURE.md #1-#2).

Each run gets its own database file if `database.path` in the config contains
a `{run_id}` placeholder (the shipped default does) -- see
docs/requirements/2026-08-27-per-run-db-and-background-run-scripts/. Stop
with SIGINT/SIGTERM for a graceful shutdown (writer drained, DB closed).

Usage:
    python -m src.main [--config config/settings.yaml]

For running detached in the background with start/stop/status, see
scripts/collector.sh.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
from datetime import datetime, timezone

import aiohttp

from .config import load_settings, resolve_db_path, resolve_path_template
from .connectors import coinm, options, spot, usdm
from .connectors.market import ConnectorContext
from .connectors.system_status import system_status_loop
from .binance_client import RestClient
from .clickhouse_sink import ClickHouseSink
from .gap_fill import gap_fill_loop
from .ratelimit import RestWeightLimiter, WsConnectionLimiter
from .raw_archive import RawArchiveWriter
from .storage import DBWriter, open_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("main")

RUNNERS = {
    "spot": spot.run,
    "usdm_futures": usdm.run,
    "coinm_futures": coinm.run,
    "options": options.run,
}


def _run_id() -> str:
    return os.environ.get("RUN_ID") or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


async def run(config_path: str, duration_seconds: float | None = None) -> None:
    settings = load_settings(config_path)
    run_id = _run_id()
    db_path = resolve_db_path(settings.database_path, run_id)
    logger.info("Run %s starting. Writing to database: %s", run_id, db_path)
    # Expose for wrappers / validation scripts
    os.environ["BMO_RUN_ID"] = run_id
    os.environ["BMO_DB_PATH"] = db_path
    if settings.clickhouse.enabled:
        os.environ["BMO_CH_DB"] = resolve_path_template(settings.clickhouse.database, run_id)
    conn = await open_db(db_path)
    queue: asyncio.Queue = asyncio.Queue(maxsize=10000)

    raw_archive = None
    if settings.raw_archive.enabled:
        archive_path = resolve_path_template(settings.raw_archive.path, run_id)
        raw_archive = RawArchiveWriter(archive_path, rotate=settings.raw_archive.rotate)
        logger.info("Raw archive enabled: %s (rotate=%s)", archive_path, settings.raw_archive.rotate)

    clickhouse = None
    if settings.clickhouse.enabled:
        ch_db = resolve_path_template(settings.clickhouse.database, run_id)
        clickhouse = ClickHouseSink(settings.clickhouse, database=ch_db)
        logger.info("ClickHouse sink enabled: %s db=%s", settings.clickhouse.url, ch_db)

    writer = DBWriter(conn, queue, raw_archive=raw_archive, clickhouse=clickhouse)
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
                if key in ("spot", "usdm_futures", "coinm_futures"):
                    product_tasks.append(
                        asyncio.create_task(gap_fill_loop(cfg, ctx, poll_minutes=5), name=f"gap_fill_{key}")
                    )

            # Public exchange status (Spot API host); always on when any product runs.
            status_rest = RestClient(
                session,
                "https://api.binance.com",
                RestWeightLimiter(600),
            )
            # Reuse first product's queue/db via a lightweight context
            status_ctx = ConnectorContext(
                queue=queue,
                session=session,
                rest=status_rest,
                ws_limiter=WsConnectionLimiter(settings.ws_connections_per_5min),
                db=conn,
                max_streams_per_connection=settings.max_streams_per_connection,
            )
            product_tasks.append(asyncio.create_task(system_status_loop(status_rest, status_ctx, poll_minutes=5), name="exchange_status"))

            stop = asyncio.Event()
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                try:
                    loop.add_signal_handler(sig, stop.set)
                except NotImplementedError:
                    pass  # not available on all platforms

            try:
                if duration_seconds is not None and duration_seconds > 0:
                    logger.info("Timed run: stopping after %.0f seconds", duration_seconds)
                    try:
                        await asyncio.wait_for(stop.wait(), timeout=duration_seconds)
                    except asyncio.TimeoutError:
                        logger.info("Duration elapsed, stopping connectors...")
                        stop.set()
                else:
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
        durable_elsewhere = settings.clickhouse.enabled or settings.raw_archive.enabled
        if not settings.database_persist and durable_elsewhere:
            for suffix in ("", "-wal", "-shm"):
                path = db_path + suffix
                try:
                    if os.path.exists(path):
                        os.remove(path)
                        logger.info("Removed non-persistent SQLite file: %s", path)
                except OSError as exc:
                    logger.warning("Could not remove %s: %s", path, exc)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/settings.yaml")
    parser.add_argument(
        "--duration-seconds",
        type=float,
        default=None,
        help="Stop automatically after N seconds (smoke / timed captures).",
    )
    args = parser.parse_args()
    asyncio.run(run(args.config, duration_seconds=args.duration_seconds))


if __name__ == "__main__":
    main()
