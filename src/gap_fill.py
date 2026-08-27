"""Historical REST gap-fill crawler.

Detects holes in stored agg_trades IDs and candle open_times, fetches public
Binance historical endpoints, and enqueues envelopes with
`source_type=rest_backfill`. Never overwrites an existing live observation
(UNIQUE + INSERT OR IGNORE / backfill-safe candle insert).

Individual trade historicalTrades requires an API key — out of scope.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from .connectors.common import parse_agg_trade
from .connectors.market import ConnectorContext
from .config import ProductConfig
from .models import Envelope
from .storage import log_system_event

logger = logging.getLogger(__name__)

# product tag → (aggTrades path, klines path, weight hints)
REST_PATHS: dict[str, tuple[str, str]] = {
    "SPOT": ("/api/v3/aggTrades", "/api/v3/klines"),
    "USDM_FUTURES": ("/fapi/v1/aggTrades", "/fapi/v1/klines"),
    "COINM_FUTURES": ("/dapi/v1/aggTrades", "/dapi/v1/klines"),
}

INTERVAL_MS = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "2h": 7_200_000,
    "4h": 14_400_000,
    "6h": 21_600_000,
    "8h": 28_800_000,
    "12h": 43_200_000,
    "1d": 86_400_000,
    "3d": 259_200_000,
    "1w": 604_800_000,
}


def parse_kline_rest(row: list[Any], interval: str) -> dict[str, Any]:
    return {
        "interval": interval,
        "open_time": int(row[0]),
        "close_time": int(row[6]),
        "open": str(row[1]),
        "high": str(row[2]),
        "low": str(row[3]),
        "close": str(row[4]),
        "base_volume": str(row[5]),
        "quote_volume": str(row[7]),
        "trade_count": int(row[8]) if row[8] is not None else None,
        "taker_buy_base_volume": str(row[9]) if len(row) > 9 else None,
        "taker_buy_quote_volume": str(row[10]) if len(row) > 10 else None,
        "is_final": True,
    }


def find_id_gaps(ids: list[int], max_gap_span: int = 5000) -> list[tuple[int, int]]:
    """Return inclusive (missing_start, missing_end) ranges between sorted ids."""
    if len(ids) < 2:
        return []
    gaps: list[tuple[int, int]] = []
    for a, b in zip(ids, ids[1:]):
        if b <= a + 1:
            continue
        # Cap enormous holes (e.g. cold start) so we don't hammer REST forever.
        if b - a - 1 > max_gap_span:
            continue
        gaps.append((a + 1, b - 1))
    return gaps


def find_open_time_gaps(times: list[int], step_ms: int, max_missing: int = 500) -> list[tuple[int, int]]:
    """Return (missing_start, missing_end_inclusive) open_time ranges."""
    if len(times) < 2 or step_ms <= 0:
        return []
    gaps: list[tuple[int, int]] = []
    for a, b in zip(times, times[1:]):
        if b <= a + step_ms:
            continue
        missing = (b - a) // step_ms - 1
        if missing <= 0 or missing > max_missing:
            continue
        gaps.append((a + step_ms, b - step_ms))
    return gaps


async def _job(
    ctx: ConnectorContext,
    product: str,
    symbol: str,
    feed: str,
    gap_start: int | None,
    gap_end: int | None,
    status: str,
    rows_inserted: int = 0,
    detail: str = "",
) -> None:
    await ctx.queue.put(
        Envelope(
            product=product,
            stream_name="gap_fill",
            source_endpoint="internal",
            kind="gap_fill_job",
            payload={
                "feed": feed,
                "gap_start": gap_start,
                "gap_end": gap_end,
                "status": status,
                "rows_inserted": rows_inserted,
                "detail": detail,
            },
            symbol=symbol,
        )
    )


async def _symbols_to_scan(conn, product: str) -> list[str]:
    cur = await conn.execute(
        """
        SELECT symbol FROM (
          SELECT symbol FROM agg_trades WHERE product=?
          UNION SELECT symbol FROM candles WHERE product=?
          UNION SELECT symbol FROM trades WHERE product=?
        ) ORDER BY 1 LIMIT 50
        """,
        (product, product, product),
    )
    return [r[0] for r in await cur.fetchall()]


async def fill_agg_trade_gaps(
    cfg: ProductConfig,
    ctx: ConnectorContext,
    agg_path: str,
    symbol: str,
    lookback: int = 3000,
) -> int:
    cur = await ctx.db.execute(
        """
        SELECT agg_trade_id FROM agg_trades
        WHERE product=? AND symbol=?
        ORDER BY agg_trade_id DESC LIMIT ?
        """,
        (cfg.tag, symbol, lookback),
    )
    ids = sorted(r[0] for r in await cur.fetchall())
    gaps = find_id_gaps(ids)
    inserted_total = 0
    for gap_start, gap_end in gaps[:20]:
        await _job(ctx, cfg.tag, symbol, "agg_trades", gap_start, gap_end, "detected")
        await log_system_event(
            ctx.db,
            "gap_detected",
            detail=f"agg_trades {gap_start}-{gap_end}",
            product=cfg.tag,
            symbol=symbol,
        )
        from_id = gap_start
        got = 0
        try:
            while from_id <= gap_end:
                rows = await ctx.rest.get_json(
                    agg_path,
                    weight=20,
                    params={"symbol": symbol, "fromId": from_id, "limit": 1000},
                )
                if not rows:
                    break
                stop = False
                for row in rows:
                    parsed = parse_agg_trade(row)
                    aid = int(parsed["agg_trade_id"])
                    if aid < gap_start:
                        continue
                    if aid > gap_end:
                        stop = True
                        break
                    await ctx.queue.put(
                        Envelope(
                            product=cfg.tag,
                            stream_name="rest_backfill_aggTrades",
                            source_endpoint=cfg.rest_base_url + agg_path,
                            kind="agg_trade",
                            payload=parsed,
                            symbol=symbol,
                            source_type="rest_backfill",
                        )
                    )
                    got += 1
                    from_id = aid + 1
                if stop:
                    break
                last = rows[-1].get("a")
                if last is None:
                    break
                nxt = int(last) + 1
                if nxt <= from_id:
                    break
                from_id = nxt
            status = "recovered" if got and from_id > gap_end else ("partial" if got else "skipped")
            await _job(ctx, cfg.tag, symbol, "agg_trades", gap_start, gap_end, status, got)
            if got:
                await log_system_event(
                    ctx.db,
                    "gap_recovered",
                    detail=f"agg_trades {gap_start}-{gap_end} inserted≈{got} status={status}",
                    product=cfg.tag,
                    symbol=symbol,
                )
            inserted_total += got
        except Exception as exc:  # noqa: BLE001
            logger.exception("agg trade gap fill failed %s %s", cfg.tag, symbol)
            await _job(
                ctx, cfg.tag, symbol, "agg_trades", gap_start, gap_end, "failed", got, detail=str(exc)
            )
            await log_system_event(
                ctx.db, "rest_failure", detail=f"gap_fill aggTrades: {exc}", product=cfg.tag, symbol=symbol
            )
    return inserted_total


async def fill_candle_gaps(
    cfg: ProductConfig,
    ctx: ConnectorContext,
    klines_path: str,
    symbol: str,
    lookback_bars: int = 500,
) -> int:
    inserted_total = 0
    for interval in cfg.kline_intervals:
        step = INTERVAL_MS.get(interval)
        if not step:
            continue
        cur = await ctx.db.execute(
            """
            SELECT open_time FROM candles
            WHERE product=? AND symbol=? AND interval=?
            ORDER BY open_time DESC LIMIT ?
            """,
            (cfg.tag, symbol, interval, lookback_bars),
        )
        times = sorted(r[0] for r in await cur.fetchall())
        gaps = find_open_time_gaps(times, step)
        for gap_start, gap_end in gaps[:10]:
            await _job(ctx, cfg.tag, symbol, "candles", gap_start, gap_end, "detected", detail=interval)
            got = 0
            try:
                rows = await ctx.rest.get_json(
                    klines_path,
                    weight=5,
                    params={
                        "symbol": symbol,
                        "interval": interval,
                        "startTime": gap_start,
                        "endTime": gap_end + step - 1,
                        "limit": 1000,
                    },
                )
                for row in rows or []:
                    parsed = parse_kline_rest(row, interval)
                    if parsed["open_time"] < gap_start or parsed["open_time"] > gap_end:
                        continue
                    await ctx.queue.put(
                        Envelope(
                            product=cfg.tag,
                            stream_name="rest_backfill_klines",
                            source_endpoint=cfg.rest_base_url + klines_path,
                            kind="candle",
                            payload=parsed,
                            symbol=symbol,
                            source_type="rest_backfill",
                        )
                    )
                    got += 1
                status = "recovered" if got else "skipped"
                await _job(
                    ctx, cfg.tag, symbol, "candles", gap_start, gap_end, status, got, detail=interval
                )
                if got:
                    await log_system_event(
                        ctx.db,
                        "gap_recovered",
                        detail=f"candles {interval} {gap_start}-{gap_end} inserted≈{got}",
                        product=cfg.tag,
                        symbol=symbol,
                    )
                inserted_total += got
            except Exception as exc:  # noqa: BLE001
                logger.exception("candle gap fill failed %s %s %s", cfg.tag, symbol, interval)
                await _job(
                    ctx,
                    cfg.tag,
                    symbol,
                    "candles",
                    gap_start,
                    gap_end,
                    "failed",
                    got,
                    detail=f"{interval}: {exc}",
                )
                await log_system_event(
                    ctx.db, "rest_failure", detail=f"gap_fill klines: {exc}", product=cfg.tag, symbol=symbol
                )
    return inserted_total


async def gap_fill_loop(
    cfg: ProductConfig,
    ctx: ConnectorContext,
    poll_minutes: int = 5,
) -> None:
    paths = REST_PATHS.get(cfg.tag)
    if not paths:
        return
    agg_path, klines_path = paths
    # First pass after a short settle so live streams have written some rows.
    await asyncio.sleep(30)
    while True:
        try:
            symbols = await _symbols_to_scan(ctx.db, cfg.tag)
            if cfg.symbol_universe == "list" and cfg.symbol_list:
                allowed = {s.upper() for s in cfg.symbol_list}
                symbols = [s for s in symbols if s.upper() in allowed] or [s.upper() for s in cfg.symbol_list]
            for symbol in symbols:
                await fill_agg_trade_gaps(cfg, ctx, agg_path, symbol)
                await fill_candle_gaps(cfg, ctx, klines_path, symbol)
        except Exception:  # noqa: BLE001
            logger.exception("gap_fill loop error for %s", cfg.tag)
        await asyncio.sleep(max(poll_minutes, 1) * 60)
