"""Payload parsers shared across Spot, USDS-M, and COIN-M -- Binance uses the
same field layout for trades, book ticker, 24h ticker, klines, and depth
diffs across these three products, differing mainly in a few futures-only
fields (`pu` on depth diffs, contract-specific streams like markPrice/
forceOrder). Options payloads differ enough to warrant their own parsing
(see options.py).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any


def _mul(a: str, b: str) -> str:
    return str(Decimal(a) * Decimal(b))


def parse_trade(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "trade_id": data["t"],
        "event_time": data.get("E"),
        "trade_time": data["T"],
        "price": data["p"],
        "quantity": data["q"],
        "quote_quantity": _mul(data["p"], data["q"]),
        "buyer_maker": bool(data["m"]),
    }


def parse_agg_trade(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "agg_trade_id": data["a"],
        "first_trade_id": data.get("f"),
        "last_trade_id": data.get("l"),
        "price": data["p"],
        "quantity": data["q"],
        "trade_time": data["T"],
        "event_time": data.get("E"),
        "buyer_maker": bool(data["m"]),
    }


def parse_book_ticker(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "update_id": data.get("u"),
        "best_bid_price": data["b"],
        "best_bid_qty": data["B"],
        "best_ask_price": data["a"],
        "best_ask_qty": data["A"],
    }


def parse_ticker_24h(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "price_change": data.get("p"),
        "price_change_percent": data.get("P"),
        "weighted_avg_price": data.get("w"),
        "last_price": data.get("c"),
        "open_price": data.get("o"),
        "high_price": data.get("h"),
        "low_price": data.get("l"),
        "base_volume": data.get("v"),
        "quote_volume": data.get("q"),
        "open_time": data.get("O"),
        "close_time": data.get("C"),
        "event_time": data.get("E"),
        "first_trade_id": data.get("F"),
        "last_trade_id": data.get("L"),
        "trade_count": data.get("n"),
    }


def parse_kline(data: dict[str, Any]) -> dict[str, Any]:
    k = data["k"]
    return {
        "interval": k["i"],
        "open_time": k["t"],
        "close_time": k["T"],
        "open": k["o"],
        "high": k["h"],
        "low": k["l"],
        "close": k["c"],
        "base_volume": k["v"],
        "quote_volume": k["q"],
        "trade_count": k.get("n"),
        "taker_buy_base_volume": k.get("V"),
        "taker_buy_quote_volume": k.get("Q"),
        "is_final": bool(k.get("x", False)),
    }


def parse_depth_diff(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "first_update_id": data["U"],
        "final_update_id": data["u"],
        "prev_final_update_id": data.get("pu"),
        "bids": data.get("b", []),
        "asks": data.get("a", []),
        "event_time": data.get("E"),
    }


def parse_depth_snapshot(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "last_update_id": data["lastUpdateId"],
        "bids": data.get("bids", []),
        "asks": data.get("asks", []),
        # Present on futures' REST depth snapshot response; absent on spot's,
        # which genuinely doesn't return them.
        "event_time": data.get("E"),
        "transaction_time": data.get("T"),
    }


def parse_mark_price(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "mark_price": data["p"],
        "index_price": data.get("i"),
        "estimated_settle_price": data.get("P"),
        "funding_rate": data.get("r"),
        "next_funding_time": data.get("T"),
        "event_time": data.get("E"),
    }


def funding_from_mark_price(mp: dict[str, Any]) -> dict[str, Any] | None:
    """The markPriceUpdate stream carries the current funding rate and next
    funding time; reuse it instead of separately polling the funding-rate
    REST endpoint (saves REST weight budget)."""
    if mp.get("funding_rate") is None or mp.get("next_funding_time") is None:
        return None
    return {
        "funding_rate": mp["funding_rate"],
        "funding_time": mp["next_funding_time"],
        "mark_price": mp["mark_price"],
    }


def parse_force_order(data: dict[str, Any]) -> dict[str, Any]:
    o = data["o"]
    return {
        "side": o["S"],
        "order_type": o.get("o"),
        "price": o["p"],
        "avg_price": o.get("ap"),
        "quantity": o["q"],
        "order_status": o.get("X"),
        "event_time": data.get("E"),
    }


def _filter_value(filters: list[dict], filter_type: str, field: str) -> str | None:
    for f in filters:
        if f.get("filterType") == filter_type:
            return f.get(field)
    return None


def parse_symbol_info(sym: dict[str, Any]) -> dict[str, Any]:
    filters = sym.get("filters", [])
    out = {
        "status": sym.get("status"),
        "base_asset": sym.get("baseAsset"),
        "quote_asset": sym.get("quoteAsset"),
        "contract_type": sym.get("contractType"),
        "tick_size": _filter_value(filters, "PRICE_FILTER", "tickSize"),
        "step_size": _filter_value(filters, "LOT_SIZE", "stepSize"),
        "min_qty": _filter_value(filters, "LOT_SIZE", "minQty"),
        "min_notional": _filter_value(filters, "NOTIONAL", "minNotional")
        or _filter_value(filters, "MIN_NOTIONAL", "minNotional"),
    }
    if "isMarginTradingAllowed" in sym:
        out["margin_tradable"] = bool(sym["isMarginTradingAllowed"])
    return out


def parse_open_interest(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "open_interest": data["openInterest"],
        "observation_time": data.get("time"),
    }


# Each positioning endpoint's primary ratio field has a different name; the
# raw payload is preserved regardless (see storage._write_futures_positioning),
# this just says which field is "the value" for the requested no-interpretation
# storage: {timestamp, symbol, metric, value, source, raw payload}.
POSITIONING_VALUE_FIELDS = {
    "globalLongShortAccountRatio": "longShortRatio",
    "topLongShortAccountRatio": "longShortRatio",
    "topLongShortPositionRatio": "longShortRatio",
    "takerlongshortRatio": "buySellRatio",
}


def parse_positioning_entry(metric: str, entry: dict[str, Any]) -> dict[str, Any]:
    value_field = POSITIONING_VALUE_FIELDS.get(metric)
    return {
        "value": entry.get(value_field) if value_field else None,
        "observation_time": entry.get("timestamp"),
    }


def positioning_rows(metric: str, entry: dict[str, Any]) -> list[dict[str, Any]]:
    """Expand one REST positioning payload into one or more storage rows.

    Most endpoints are a single ratio → one row. COIN-M's `takerBuySellVol`
    exposes buy/sell *volumes* (no ratio field); emit both as separate
    metrics so `futures_positioning.value` stays NOT NULL without inventing
    a ratio.
    """
    if metric == "takerBuySellVol":
        ts = entry.get("timestamp")
        return [
            {"metric": "takerBuyVol", "value": entry.get("takerBuyVol"), "observation_time": ts, "raw": entry},
            {"metric": "takerSellVol", "value": entry.get("takerSellVol"), "observation_time": ts, "raw": entry},
        ]
    parsed = parse_positioning_entry(metric, entry)
    return [
        {
            "metric": metric,
            "value": parsed["value"],
            "observation_time": parsed["observation_time"],
            "raw": entry,
        }
    ]


def coinm_pair_from_symbol(symbol: str) -> str:
    """Map a COIN-M contract symbol to the `pair` query param Binance's
    `/futures/data/*` endpoints expect (e.g. BTCUSD_PERP / BTCUSD_250926 → BTCUSD)."""
    s = symbol.upper()
    if s.endswith("_PERP"):
        return s[: -len("_PERP")]
    parts = s.rsplit("_", 1)
    if len(parts) == 2 and parts[1].isdigit():
        return parts[0]
    return s