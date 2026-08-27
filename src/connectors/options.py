"""Binance Options (European Options) connector.

Options' public WS/REST payload shapes are the least standardized of the
four products and could not be verified against Binance's live docs from
this sandbox (outbound network to Binance is blocked here -- see
STATUS.md/CHANGELOG.md). To avoid fabricating a normalized schema from
guessed field names, this connector only guarantees raw fidelity: every
message is preserved in raw_events under its real stream name, but nothing
is written to a normalized table. Confirm the current wire format against
Binance's live Options API docs and add normalizers (see connectors/common.py
for the pattern spot/usdm/coinm use) before relying on normalized Options
tables. Disabled by default in config/registry.yaml (docs/THESIS.md Phase 4).
"""

from __future__ import annotations

import asyncio
import logging

from ..binance_client import ws_messages
from ..config import ProductConfig
from ..models import Envelope
from ..ratelimit import chunk_symbols
from ..storage import log_system_event
from .market import ConnectorContext

logger = logging.getLogger(__name__)

EXCHANGE_INFO_PATH = "/eapi/v1/exchangeInfo"


async def instruments_loop(cfg: ProductConfig, ctx: ConnectorContext) -> None:
    while True:
        try:
            data = await ctx.rest.get_json(EXCHANGE_INFO_PATH, weight=1)
            for sym in data.get("optionSymbols", []):
                await ctx.queue.put(
                    Envelope(
                        product=cfg.tag,
                        stream_name="exchangeInfo",
                        source_endpoint=cfg.rest_base_url + EXCHANGE_INFO_PATH,
                        kind="instrument_snapshot",
                        payload={
                            "status": sym.get("status"),
                            "base_asset": sym.get("underlying"),
                            "quote_asset": sym.get("quoteAsset"),
                            "contract_type": sym.get("side") or sym.get("contractType"),
                        },
                        symbol=sym.get("symbol"),
                    )
                )
        except Exception as exc:  # noqa: BLE001
            logger.exception("options instruments poll failed")
            await log_system_event(ctx.db, "rest_failure", detail=f"instruments: {exc}", product=cfg.tag)
        await asyncio.sleep(max(cfg.instrument_poll_minutes, 1) * 60)


async def _symbol_universe(cfg: ProductConfig, ctx: ConnectorContext) -> list[str]:
    if cfg.symbol_universe == "list":
        return [s.lower() for s in cfg.symbol_list]
    data = await ctx.rest.get_json(EXCHANGE_INFO_PATH, weight=1)
    return [s["symbol"].lower() for s in data.get("optionSymbols", []) if s.get("status") in (None, "ONLINE", "TRADING")]


async def raw_stream_worker(cfg: ProductConfig, ctx: ConnectorContext, stream_names: list[str], group_id: int) -> None:
    if not stream_names:
        return
    url = f"{cfg.ws_base_url}/stream?streams=" + "/".join(stream_names)
    async for event, data in ws_messages(ctx.session, url, ctx.ws_limiter):
        if event == "connected":
            await log_system_event(ctx.db, "ws_connected", detail=f"options group={group_id} streams={len(stream_names)}", product=cfg.tag)
        elif event == "message":
            stream = data.get("stream", "")
            payload = data.get("data", {})
            symbol = payload.get("s")
            kind = "options_" + stream.split("@")[-1].split("_")[0] if "@" in stream else "options_unknown"
            await ctx.queue.put(
                Envelope(product=cfg.tag, stream_name=stream, source_endpoint=cfg.ws_base_url, kind=kind, payload=payload, symbol=symbol)
            )
        elif event in ("disconnected", "error", "reconnect_scheduled"):
            await log_system_event(ctx.db, "ws_reconnect", detail=f"options group={group_id} reason={event}:{data}", product=cfg.tag)


async def broad_supervisor(cfg: ProductConfig, ctx: ConnectorContext) -> None:
    while True:
        try:
            symbols = await _symbol_universe(cfg, ctx)
        except Exception as exc:  # noqa: BLE001
            logger.exception("options universe fetch failed")
            await log_system_event(ctx.db, "rest_failure", detail=f"universe: {exc}", product=cfg.tag)
            await asyncio.sleep(30)
            continue

        stream_names: list[str] = []
        for s in symbols:
            stream_names += [f"{s}@trade", f"{s}@ticker"]
            for interval in cfg.kline_intervals:
                stream_names.append(f"{s}@kline_{interval}")
        chunks = chunk_symbols(stream_names, ctx.max_streams_per_connection)
        tasks = [asyncio.create_task(raw_stream_worker(cfg, ctx, chunk, i)) for i, chunk in enumerate(chunks)]

        await asyncio.sleep(max(cfg.instrument_poll_minutes, 1) * 60)
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def run(cfg: ProductConfig, ctx: ConnectorContext) -> None:
    await asyncio.gather(instruments_loop(cfg, ctx), broad_supervisor(cfg, ctx))
