"""Binance Options (European Options) connector.

Live-verified 2026-08-27 against eapi.binance.com:
- REST exchangeInfo / trades / ticker / mark (incl. IV+Greeks) / index work.
- Official WS host `wss://nbstream.binance.com/eoptions` returns HTTP 404 from
  this network; `wss://fstream.binancefuture.com/eoptions` accepts the handshake
  but delivered no frames in probes — so REST is the primary Options path here,
  with WS kept best-effort for environments where it works.
- Option stream symbols must keep Binance's mixed-case form (do not lower).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from ..binance_client import ws_messages
from ..config import ProductConfig
from ..models import Envelope
from ..ratelimit import chunk_symbols
from ..storage import log_system_event
from .market import ConnectorContext

logger = logging.getLogger(__name__)

EXCHANGE_INFO_PATH = "/eapi/v1/exchangeInfo"


def parse_option_symbol(sym: dict[str, Any]) -> dict[str, Any]:
    filters = sym.get("filters") or []
    tick = step = min_qty = None
    for f in filters:
        ft = f.get("filterType")
        if ft == "PRICE_FILTER":
            tick = f.get("tickSize")
        elif ft == "LOT_SIZE":
            step = f.get("stepSize")
            min_qty = f.get("minQty")
    return {
        "status": sym.get("status"),
        "base_asset": sym.get("underlying"),
        "quote_asset": sym.get("quoteAsset"),
        "contract_type": sym.get("side"),  # CALL / PUT
        "tick_size": tick,
        "step_size": step,
        "min_qty": min_qty or sym.get("minQty"),
        "min_notional": None,
        "strike_price": sym.get("strikePrice"),
        "expiry_date": sym.get("expiryDate"),
        "underlying_type": sym.get("underlyingType"),
        "raw": sym,
    }


def parse_option_trade(row: dict[str, Any]) -> dict[str, Any]:
    # Options REST trade: tradeId, price, qty, time, side (+1 buy / -1 sell).
    # buyer_maker is not supplied; store False and keep side in quote_quantity unused —
    # raw payload preserves side.
    return {
        "trade_id": int(row["tradeId"]),
        "event_time": row.get("time"),
        "trade_time": int(row["time"]),
        "price": str(row["price"]),
        "quantity": str(row["qty"]),
        "quote_quantity": str(row.get("quoteQty")) if row.get("quoteQty") is not None else None,
        "buyer_maker": False,
    }


def parse_option_ticker(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "price_change": row.get("priceChange"),
        "price_change_percent": row.get("priceChangePercent"),
        "weighted_avg_price": None,
        "last_price": row.get("lastPrice"),
        "open_price": row.get("open"),
        "high_price": row.get("high"),
        "low_price": row.get("low"),
        "base_volume": row.get("volume"),
        "quote_volume": row.get("amount"),
        "open_time": row.get("openTime"),
        "close_time": row.get("closeTime"),
        "event_time": row.get("closeTime"),
        "first_trade_id": row.get("firstTradeId"),
        "last_trade_id": None,
        "trade_count": row.get("tradeCount"),
    }


def parse_option_mark(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "mark_price": row.get("markPrice"),
        "mark_iv": row.get("markIV"),
        "bid_iv": row.get("bidIV"),
        "ask_iv": row.get("askIV"),
        "delta": row.get("delta"),
        "gamma": row.get("gamma"),
        "theta": row.get("theta"),
        "vega": row.get("vega"),
        "raw": row,
    }


def parse_option_depth(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "last_update_id": int(data["lastUpdateId"]),
        "bids": data.get("bids") or [],
        "asks": data.get("asks") or [],
        "transaction_time": data.get("T"),
        "event_time": None,
    }


def parse_option_open_interest(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "open_interest": str(row["sumOpenInterest"]),
        "observation_time": int(row["timestamp"]) if row.get("timestamp") is not None else None,
    }


def option_symbol_parts(symbol: str) -> tuple[str, str] | None:
    """BTC-260828-65000-C → (underlyingAsset BTC, expiration 260828)."""
    parts = symbol.split("-")
    if len(parts) < 4:
        return None
    return parts[0], parts[1]


async def instruments_loop(cfg: ProductConfig, ctx: ConnectorContext) -> None:
    while True:
        try:
            data = await ctx.rest.get_json(EXCHANGE_INFO_PATH, weight=1)
            allow = set(cfg.symbol_list) if cfg.symbol_universe == "list" else None
            for sym in data.get("optionSymbols", []):
                if allow is not None and sym.get("symbol") not in allow:
                    continue
                parsed = parse_option_symbol(sym)
                payload = {k: v for k, v in parsed.items() if k != "raw"}
                payload["raw_symbol"] = sym
                await ctx.queue.put(
                    Envelope(
                        product=cfg.tag,
                        stream_name="exchangeInfo",
                        source_endpoint=cfg.rest_base_url + EXCHANGE_INFO_PATH,
                        kind="instrument_snapshot",
                        payload=payload,
                        symbol=sym.get("symbol"),
                    )
                )
        except Exception as exc:  # noqa: BLE001
            logger.exception("options instruments poll failed")
            await log_system_event(ctx.db, "rest_failure", detail=f"instruments: {exc}", product=cfg.tag)
        await asyncio.sleep(max(cfg.instrument_poll_minutes, 1) * 60)


async def _symbol_universe(cfg: ProductConfig, ctx: ConnectorContext) -> list[str]:
    if cfg.symbol_universe == "list":
        return list(cfg.symbol_list)  # preserve case
    data = await ctx.rest.get_json(EXCHANGE_INFO_PATH, weight=1)
    return [
        s["symbol"]
        for s in data.get("optionSymbols", [])
        if s.get("status") in (None, "ONLINE", "TRADING")
    ]


async def rest_market_loop(cfg: ProductConfig, ctx: ConnectorContext, symbols_provider) -> None:
    """Polls public Options REST market endpoints for the configured symbol set."""
    while True:
        symbols = symbols_provider()
        underlyings: set[str] = set()
        for symbol in symbols:
            try:
                trades = await ctx.rest.get_json("/eapi/v1/trades", weight=5, params={"symbol": symbol, "limit": 20})
                for row in trades or []:
                    await ctx.queue.put(
                        Envelope(
                            product=cfg.tag,
                            stream_name="rest_trades",
                            source_endpoint=cfg.rest_base_url + "/eapi/v1/trades",
                            kind="trade",
                            payload=parse_option_trade(row),
                            symbol=symbol,
                        )
                    )
            except Exception as exc:  # noqa: BLE001
                logger.exception("options trades poll failed for %s", symbol)
                await log_system_event(ctx.db, "rest_failure", detail=f"options trades {symbol}: {exc}", product=cfg.tag, symbol=symbol)

            try:
                tickers = await ctx.rest.get_json("/eapi/v1/ticker", weight=5, params={"symbol": symbol})
                if isinstance(tickers, dict):
                    tickers = [tickers]
                for row in tickers or []:
                    await ctx.queue.put(
                        Envelope(
                            product=cfg.tag,
                            stream_name="rest_ticker",
                            source_endpoint=cfg.rest_base_url + "/eapi/v1/ticker",
                            kind="ticker_24h",
                            payload=parse_option_ticker(row),
                            symbol=symbol,
                        )
                    )
            except Exception as exc:  # noqa: BLE001
                logger.exception("options ticker poll failed for %s", symbol)
                await log_system_event(ctx.db, "rest_failure", detail=f"options ticker {symbol}: {exc}", product=cfg.tag, symbol=symbol)

            try:
                marks = await ctx.rest.get_json("/eapi/v1/mark", weight=5, params={"symbol": symbol})
                if isinstance(marks, dict):
                    marks = [marks]
                for row in marks or []:
                    await ctx.queue.put(
                        Envelope(
                            product=cfg.tag,
                            stream_name="rest_mark",
                            source_endpoint=cfg.rest_base_url + "/eapi/v1/mark",
                            kind="options_mark",
                            payload=parse_option_mark(row),
                            symbol=symbol,
                        )
                    )
            except Exception as exc:  # noqa: BLE001
                logger.exception("options mark poll failed for %s", symbol)
                await log_system_event(ctx.db, "rest_failure", detail=f"options mark {symbol}: {exc}", product=cfg.tag, symbol=symbol)

            try:
                depth = await ctx.rest.get_json(
                    "/eapi/v1/depth", weight=1, params={"symbol": symbol, "limit": 100}
                )
                await ctx.queue.put(
                    Envelope(
                        product=cfg.tag,
                        stream_name="rest_depth",
                        source_endpoint=cfg.rest_base_url + "/eapi/v1/depth",
                        kind="depth_snapshot",
                        payload=parse_option_depth(depth),
                        symbol=symbol,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("options depth poll failed for %s", symbol)
                await log_system_event(ctx.db, "rest_failure", detail=f"options depth {symbol}: {exc}", product=cfg.tag, symbol=symbol)

            # Derive underlying from symbol prefix BTC-... → need exchangeInfo; use BTCUSDT heuristic from parts
            parts = symbol.split("-")
            if parts:
                underlyings.add(parts[0] + "USDT" if not parts[0].endswith("USDT") else parts[0])

        # Open interest is keyed by underlyingAsset + expiration (not single symbol).
        oi_keys: set[tuple[str, str]] = set()
        allow = set(symbols)
        for symbol in symbols:
            pair = option_symbol_parts(symbol)
            if pair:
                oi_keys.add(pair)
        for underlying_asset, expiration in sorted(oi_keys):
            try:
                rows = await ctx.rest.get_json(
                    "/eapi/v1/openInterest",
                    weight=0,
                    params={"underlyingAsset": underlying_asset, "expiration": expiration},
                )
                for row in rows or []:
                    sym = row.get("symbol")
                    if allow and sym not in allow:
                        continue
                    await ctx.queue.put(
                        Envelope(
                            product=cfg.tag,
                            stream_name="rest_openInterest",
                            source_endpoint=cfg.rest_base_url + "/eapi/v1/openInterest",
                            kind="open_interest",
                            payload={**parse_option_open_interest(row), "raw": row},
                            symbol=sym,
                        )
                    )
            except Exception as exc:  # noqa: BLE001
                logger.exception("options openInterest poll failed for %s %s", underlying_asset, expiration)
                await log_system_event(
                    ctx.db,
                    "rest_failure",
                    detail=f"options openInterest {underlying_asset}/{expiration}: {exc}",
                    product=cfg.tag,
                )

        for underlying in sorted(underlyings):
            try:
                data = await ctx.rest.get_json("/eapi/v1/index", weight=1, params={"underlying": underlying})
                await ctx.queue.put(
                    Envelope(
                        product=cfg.tag,
                        stream_name="rest_index",
                        source_endpoint=cfg.rest_base_url + "/eapi/v1/index",
                        kind="options_index",
                        payload={
                            "underlying": underlying,
                            "index_price": str(data["indexPrice"]),
                            "observation_time": data.get("time"),
                            "raw": data,
                        },
                        symbol=underlying,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("options index poll failed for %s", underlying)
                await log_system_event(ctx.db, "rest_failure", detail=f"options index {underlying}: {exc}", product=cfg.tag)

        await asyncio.sleep(60)


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

        # Cap WS fan-out: Options "all" can be thousands of contracts.
        ws_symbols = symbols[:50]
        stream_names: list[str] = []
        for s in ws_symbols:
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
    holder: dict[str, list[str]] = {"symbols": []}

    async def refresh_symbols() -> None:
        while True:
            try:
                holder["symbols"] = await _symbol_universe(cfg, ctx)
            except Exception:  # noqa: BLE001
                logger.exception("options symbol refresh failed")
            await asyncio.sleep(max(cfg.instrument_poll_minutes, 1) * 60)

    # Prime once
    try:
        holder["symbols"] = await _symbol_universe(cfg, ctx)
    except Exception:  # noqa: BLE001
        logger.exception("options initial universe failed")

    await asyncio.gather(
        instruments_loop(cfg, ctx),
        broad_supervisor(cfg, ctx),
        rest_market_loop(cfg, ctx, lambda: holder["symbols"]),
        refresh_symbols(),
    )
