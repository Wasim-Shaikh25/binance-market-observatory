"""Generic connector for Spot, USDS-M, and COIN-M -- the three products that
share Binance's combined-stream WebSocket shape and REST endpoint layout.
Each product module (spot.py/usdm.py/coinm.py) just supplies base URLs,
REST paths, and a couple of futures-only flags, then calls run_market_product.

Design (docs/requirements/2026-08-27-phase1-spot-collector/DESIGN.md):
- Broad streams (trade/aggTrade/bookTicker/ticker/kline[/markPrice]) for the
  whole symbol universe are rebuilt on each instrument-poll cycle; they are
  not diff-based so a periodic reconnect costs nothing but a short gap.
- Depth is diff-based and continuity-sensitive, so it gets its own
  persistent connection with true SUBSCRIBE/UNSUBSCRIBE control messages:
  changing which symbols are in the top-N set does not force a resync of
  symbols that stay in it.
- Futures-only extras (funding/mark price, open interest, liquidations) are
  gated by `is_futures`.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field

import aiohttp

from ..binance_client import RestClient, ws_messages
from ..config import ProductConfig
from ..depth_sync import DepthSyncTracker
from ..models import Envelope
from ..ratelimit import WsConnectionLimiter, chunk_symbols
from ..storage import log_system_event
from . import common

logger = logging.getLogger(__name__)


@dataclass
class ProductPaths:
    exchange_info_path: str
    depth_path: str
    is_futures: bool = False
    open_interest_path: str | None = None
    force_order_stream: str | None = None  # e.g. "!forceOrder@arr"
    mark_price_suffix: str | None = None  # e.g. "@markPrice@1s"
    positioning_endpoints: tuple[str, ...] = ()  # metric names, e.g. "globalLongShortAccountRatio"
    positioning_path_prefix: str = "/futures/data/"  # override per-product if the real path differs


@dataclass
class ConnectorContext:
    queue: "asyncio.Queue[Envelope]"
    session: aiohttp.ClientSession
    rest: RestClient
    ws_limiter: WsConnectionLimiter
    db: object  # aiosqlite.Connection, used only for system_events logging
    max_streams_per_connection: int
    quote_volume: dict[str, float] = field(default_factory=dict)


def build_broad_stream_names(symbols: list[str], kline_intervals: list[str], mark_price_suffix: str | None) -> list[str]:
    names: list[str] = []
    for s in symbols:
        names += [f"{s}@trade", f"{s}@aggTrade", f"{s}@bookTicker", f"{s}@ticker"]
        for interval in kline_intervals:
            names.append(f"{s}@kline_{interval}")
        if mark_price_suffix:
            names.append(f"{s}{mark_price_suffix}")
    return names


async def fetch_symbol_universe(cfg: ProductConfig, ctx: ConnectorContext, paths: ProductPaths) -> tuple[list[str], list[dict]]:
    if cfg.symbol_universe == "list":
        return [s.lower() for s in cfg.symbol_list], []
    data = await ctx.rest.get_json(paths.exchange_info_path, weight=20)
    infos = [s for s in data.get("symbols", []) if s.get("status") in ("TRADING", None)]
    return [s["symbol"].lower() for s in infos], infos


async def instruments_loop(cfg: ProductConfig, ctx: ConnectorContext, paths: ProductPaths) -> None:
    while True:
        try:
            data = await ctx.rest.get_json(paths.exchange_info_path, weight=20)
            for sym in data.get("symbols", []):
                parsed = common.parse_symbol_info(sym)
                await ctx.queue.put(
                    Envelope(
                        product=cfg.tag,
                        stream_name="exchangeInfo",
                        source_endpoint=cfg.rest_base_url + paths.exchange_info_path,
                        kind="instrument_snapshot",
                        payload=parsed,
                        symbol=sym["symbol"],
                    )
                )
        except Exception as exc:  # noqa: BLE001
            logger.exception("instruments poll failed for %s", cfg.key)
            await log_system_event(ctx.db, "rest_failure", detail=f"instruments: {exc}", product=cfg.tag)
        await asyncio.sleep(max(cfg.instrument_poll_minutes, 1) * 60)


async def handle_broad_message(cfg: ProductConfig, ctx: ConnectorContext, msg: dict) -> None:
    stream = msg.get("stream", "")
    data = msg.get("data", {})
    symbol = data.get("s")
    if stream.endswith("@trade"):
        parsed, kind = common.parse_trade(data), "trade"
    elif stream.endswith("@aggTrade"):
        parsed, kind = common.parse_agg_trade(data), "agg_trade"
    elif stream.endswith("@bookTicker"):
        parsed, kind = common.parse_book_ticker(data), "book_ticker"
    elif stream.endswith("@ticker"):
        parsed, kind = common.parse_ticker_24h(data), "ticker_24h"
        if symbol and parsed.get("quote_volume"):
            try:
                ctx.quote_volume[symbol.lower()] = float(parsed["quote_volume"])
            except ValueError:
                pass
    elif "@kline_" in stream:
        parsed, kind = common.parse_kline(data), "candle"
    elif "@markPrice" in stream:
        parsed, kind = common.parse_mark_price(data), "mark_price"
    elif data.get("e") == "forceOrder":
        parsed, kind = common.parse_force_order(data), "liquidation"
        symbol = data.get("o", {}).get("s")
    else:
        return

    await ctx.queue.put(
        Envelope(product=cfg.tag, stream_name=stream, source_endpoint=cfg.ws_base_url, kind=kind, payload=parsed, symbol=symbol)
    )
    if kind == "mark_price":
        funding = common.funding_from_mark_price(parsed)
        if funding:
            await ctx.queue.put(
                Envelope(
                    product=cfg.tag,
                    stream_name=stream,
                    source_endpoint=cfg.ws_base_url,
                    kind="funding_rate",
                    payload=funding,
                    symbol=symbol,
                )
            )


async def broad_stream_worker(cfg: ProductConfig, ctx: ConnectorContext, stream_names: list[str], group_id: int) -> None:
    if not stream_names:
        return
    url = f"{cfg.ws_base_url}/stream?streams=" + "/".join(stream_names)
    async for event, data in ws_messages(ctx.session, url, ctx.ws_limiter):
        if event == "connected":
            await log_system_event(ctx.db, "ws_connected", detail=f"broad group={group_id} streams={len(stream_names)}", product=cfg.tag)
        elif event == "message":
            await handle_broad_message(cfg, ctx, data)
        elif event in ("disconnected", "error", "reconnect_scheduled"):
            await log_system_event(ctx.db, "ws_reconnect", detail=f"broad group={group_id} reason={event}:{data}", product=cfg.tag)


async def broad_streams_supervisor(cfg: ProductConfig, ctx: ConnectorContext, paths: ProductPaths) -> None:
    """Rebuilds the broad (non-depth) stream connections each time the
    symbol universe is refreshed. Not continuity-sensitive, so a periodic
    reconnect is an acceptable, simple way to pick up new/delisted symbols."""
    while True:
        try:
            symbols, _ = await fetch_symbol_universe(cfg, ctx, paths)
        except Exception as exc:  # noqa: BLE001
            logger.exception("symbol universe fetch failed for %s", cfg.key)
            await log_system_event(ctx.db, "rest_failure", detail=f"universe: {exc}", product=cfg.tag)
            await asyncio.sleep(30)
            continue

        stream_names = build_broad_stream_names(symbols, cfg.kline_intervals, paths.mark_price_suffix)
        chunks = chunk_symbols(stream_names, ctx.max_streams_per_connection)
        tasks = [asyncio.create_task(broad_stream_worker(cfg, ctx, chunk, i)) for i, chunk in enumerate(chunks)]
        if paths.force_order_stream:
            tasks.append(asyncio.create_task(broad_stream_worker(cfg, ctx, [paths.force_order_stream], -1)))

        await asyncio.sleep(max(cfg.instrument_poll_minutes, 1) * 60)
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def select_depth_symbols(cfg: ProductConfig, ctx: ConnectorContext, universe: list[str]) -> set[str]:
    top_n = min(cfg.depth.top_n, ctx.max_streams_per_connection)
    if cfg.depth.ranking == "quote_volume" and ctx.quote_volume:
        ranked = sorted(universe, key=lambda s: ctx.quote_volume.get(s, 0.0), reverse=True)
    else:
        ranked = sorted(universe)  # deterministic fallback until ranking data / other strategies exist
    return set(ranked[:top_n])


class DepthConnectionGroup:
    """One persistent WebSocket connection carrying every depth-tracked
    symbol for a product, with dynamic SUBSCRIBE/UNSUBSCRIBE so the top-N
    set can change without dropping sync on symbols that remain in it."""

    def __init__(self, cfg: ProductConfig, ctx: ConnectorContext, paths: ProductPaths):
        self.cfg = cfg
        self.ctx = ctx
        self.paths = paths
        self.trackers: dict[str, DepthSyncTracker] = {}
        self.target: set[str] = set()
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._resyncing: set[str] = set()
        self._sub_id = 0

    async def run(self) -> None:
        url = f"{self.cfg.ws_base_url}/stream"
        async for event, data in ws_messages(self.ctx.session, url, self.ctx.ws_limiter):
            if event == "connected":
                self._ws = data
                for tracker in self.trackers.values():
                    tracker.reset()
                await log_system_event(self.ctx.db, "ws_connected", detail="depth group", product=self.cfg.tag)
                if self.target:
                    await self._send(list(self.target), "SUBSCRIBE")
            elif event == "message":
                await self._handle_message(data)
            elif event in ("disconnected", "error", "reconnect_scheduled"):
                self._ws = None
                await log_system_event(self.ctx.db, "ws_reconnect", detail=f"depth group reason={event}:{data}", product=self.cfg.tag)

    async def _send(self, symbols: list[str], method: str) -> None:
        if self._ws is None or not symbols:
            return
        self._sub_id += 1
        streams = [f"{s}@depth@100ms" for s in symbols]
        await self._ws.send_str(json.dumps({"method": method, "params": streams, "id": self._sub_id}))

    async def set_target_symbols(self, symbols: set[str]) -> None:
        added = symbols - self.target
        removed = self.target - symbols
        if removed:
            await self._send(list(removed), "UNSUBSCRIBE")
            for s in removed:
                self.trackers.pop(s, None)
        if added:
            for s in added:
                self.trackers[s] = DepthSyncTracker(s, use_pu=self.paths.is_futures)
            await self._send(list(added), "SUBSCRIBE")
        self.target = symbols

    async def _handle_message(self, msg: dict) -> None:
        if "result" in msg and "id" in msg:
            return  # SUBSCRIBE/UNSUBSCRIBE ack, nothing to store
        stream = msg.get("stream", "")
        data = msg.get("data")
        if not stream.endswith("@depth@100ms") or data is None:
            return
        symbol = stream.split("@")[0]
        parsed = common.parse_depth_diff(data)

        await self.ctx.queue.put(
            Envelope(
                product=self.cfg.tag,
                stream_name=stream,
                source_endpoint=self.cfg.ws_base_url,
                kind="depth_update",
                payload=parsed,
                symbol=symbol.upper(),
            )
        )

        tracker = self.trackers.get(symbol)
        if tracker is None:
            return
        result = tracker.apply_update(parsed)
        if result == "resync_needed":
            await log_system_event(self.ctx.db, "depth_resync", detail="update-id gap detected", product=self.cfg.tag, symbol=symbol.upper())
        if result in ("buffered", "resync_needed") and symbol not in self._resyncing:
            self._resyncing.add(symbol)
            asyncio.create_task(self._resync(symbol, tracker))

    async def _resync(self, symbol: str, tracker: DepthSyncTracker) -> None:
        try:
            data = await self.ctx.rest.get_json(
                self.paths.depth_path, weight=50, params={"symbol": symbol.upper(), "limit": 1000}
            )
            snap = common.parse_depth_snapshot(data)
            tracker.apply_snapshot(snap["last_update_id"], snap["bids"], snap["asks"])
            await self.ctx.queue.put(
                Envelope(
                    product=self.cfg.tag,
                    stream_name=f"{symbol}@depth_snapshot",
                    source_endpoint=self.cfg.rest_base_url + self.paths.depth_path,
                    kind="depth_snapshot",
                    payload=snap,
                    symbol=symbol.upper(),
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("depth snapshot fetch failed for %s", symbol)
            await log_system_event(
                self.ctx.db, "rest_failure", detail=f"depth snapshot {symbol}: {exc}", product=self.cfg.tag, symbol=symbol.upper()
            )
        finally:
            self._resyncing.discard(symbol)


async def _record_coverage_tiers(cfg: ProductConfig, ctx: ConnectorContext, universe: list[str], high_res: set[str]) -> None:
    """One row per universe symbol per depth-refresh cycle, tagging it BROAD
    or HIGH_RESOLUTION -- an explicit, queryable record of which tier each
    symbol had at each point in time (docs/requirements/2026-08-27-
    positioning-coverage-tiers-and-timestamp-audit/)."""
    for symbol in universe:
        tier = "HIGH_RESOLUTION" if symbol in high_res else "BROAD"
        await ctx.queue.put(
            Envelope(
                product=cfg.tag,
                stream_name="coverage_tier",
                source_endpoint="internal",
                kind="symbol_coverage",
                payload={"tier": tier},
                symbol=symbol.upper(),
            )
        )


async def depth_supervisor(cfg: ProductConfig, ctx: ConnectorContext, paths: ProductPaths, holder: dict) -> None:
    """Runs the persistent depth connection and periodically refreshes its
    target symbol set. `holder["group"]` is exposed so other loops (e.g.
    open-interest polling) can piggyback on the same depth-tracked symbol
    set without recomputing it themselves. Also records each cycle's
    coverage-tier assignment for the whole universe, not just the
    depth-tracked subset."""
    group = DepthConnectionGroup(cfg, ctx, paths)
    holder["group"] = group
    run_task = asyncio.create_task(group.run()) if cfg.depth.enabled else None
    try:
        while True:
            try:
                universe, _ = await fetch_symbol_universe(cfg, ctx, paths)
            except Exception as exc:  # noqa: BLE001
                logger.exception("depth universe fetch failed for %s", cfg.key)
                await log_system_event(ctx.db, "rest_failure", detail=f"depth universe: {exc}", product=cfg.tag)
                await asyncio.sleep(30)
                continue
            high_res = select_depth_symbols(cfg, ctx, universe) if cfg.depth.enabled else set()
            if run_task is not None:
                await group.set_target_symbols(high_res)
            await _record_coverage_tiers(cfg, ctx, universe, high_res)
            await asyncio.sleep(max(cfg.depth.refresh_minutes, 1) * 60)
    finally:
        if run_task is not None:
            run_task.cancel()
            await asyncio.gather(run_task, return_exceptions=True)


async def open_interest_loop(cfg: ProductConfig, ctx: ConnectorContext, paths: ProductPaths, symbols_provider) -> None:
    if not paths.open_interest_path or not cfg.open_interest_poll_minutes:
        return
    while True:
        symbols = symbols_provider()
        for symbol in symbols:
            try:
                data = await ctx.rest.get_json(paths.open_interest_path, weight=1, params={"symbol": symbol.upper()})
                await ctx.queue.put(
                    Envelope(
                        product=cfg.tag,
                        stream_name="openInterest",
                        source_endpoint=cfg.rest_base_url + paths.open_interest_path,
                        kind="open_interest",
                        payload=common.parse_open_interest(data),
                        symbol=symbol.upper(),
                    )
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("open interest poll failed for %s", symbol)
                await log_system_event(ctx.db, "rest_failure", detail=f"open_interest {symbol}: {exc}", product=cfg.tag, symbol=symbol.upper())
        await asyncio.sleep(max(cfg.open_interest_poll_minutes, 1) * 60)


async def positioning_loop(cfg: ProductConfig, ctx: ConnectorContext, paths: ProductPaths, symbols_provider) -> None:
    """Polls Binance's public futures positioning endpoints (long/short
    ratios) for the depth-tracked symbol set, storing them exactly as
    requested: timestamp, symbol, metric, value, source, raw payload --
    no interpretation. These specific endpoint paths could not be verified
    against live Binance docs from this sandbox (see STATUS.md); a wrong
    path surfaces as a visible rest_failure system_event rather than
    silently storing nothing."""
    if not paths.positioning_endpoints or not cfg.positioning_poll_minutes:
        return
    while True:
        symbols = symbols_provider()
        for symbol in symbols:
            for metric in paths.positioning_endpoints:
                endpoint = f"{paths.positioning_path_prefix}{metric}"
                try:
                    data = await ctx.rest.get_json(endpoint, weight=1, params={"symbol": symbol.upper(), "period": "5m", "limit": 1})
                    if not data:
                        continue
                    entry = data[-1]
                    parsed = common.parse_positioning_entry(metric, entry)
                    await ctx.queue.put(
                        Envelope(
                            product=cfg.tag,
                            stream_name=metric,
                            source_endpoint=cfg.rest_base_url + endpoint,
                            kind="futures_positioning",
                            payload={"metric": metric, "value": parsed["value"], "observation_time": parsed["observation_time"], "raw": entry},
                            symbol=symbol.upper(),
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.exception("positioning poll failed for %s/%s", symbol, metric)
                    await log_system_event(
                        ctx.db, "rest_failure", detail=f"positioning {metric} {symbol}: {exc}", product=cfg.tag, symbol=symbol.upper()
                    )
        await asyncio.sleep(max(cfg.positioning_poll_minutes, 1) * 60)


async def run_market_product(cfg: ProductConfig, ctx: ConnectorContext, paths: ProductPaths) -> None:
    depth_group_holder: dict[str, DepthConnectionGroup] = {}

    tasks = [
        asyncio.create_task(instruments_loop(cfg, ctx, paths)),
        asyncio.create_task(broad_streams_supervisor(cfg, ctx, paths)),
        asyncio.create_task(depth_supervisor(cfg, ctx, paths, depth_group_holder)),
    ]
    if paths.open_interest_path:
        tasks.append(
            asyncio.create_task(
                open_interest_loop(
                    cfg,
                    ctx,
                    paths,
                    lambda: list(depth_group_holder["group"].target) if "group" in depth_group_holder else [],
                )
            )
        )
    if paths.positioning_endpoints:
        tasks.append(
            asyncio.create_task(
                positioning_loop(
                    cfg,
                    ctx,
                    paths,
                    lambda: list(depth_group_holder["group"].target) if "group" in depth_group_holder else [],
                )
            )
        )
    await asyncio.gather(*tasks)
