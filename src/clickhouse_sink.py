"""Live ClickHouse sink (HTTP). Batches inserts; best-effort.

Prices/quantities stay String. raw_events.payload_json preserves evidence.
Mirrors every normalizer kind in storage._NORMALIZERS.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .config import ClickHouseSinkConfig
from .models import Envelope, resolve_source_type, taker_side

logger = logging.getLogger(__name__)

RAW_DDL = """
CREATE TABLE IF NOT EXISTS {db}.raw_events (
  exchange String,
  product String,
  symbol Nullable(String),
  stream_name String,
  source_endpoint String,
  source_type String,
  schema_version String,
  observed_at String,
  kind String,
  payload_json String
) ENGINE = MergeTree ORDER BY (product, observed_at)
"""

TABLE_DDL: dict[str, str] = {
    "instruments": """
CREATE TABLE IF NOT EXISTS {db}.instruments (
  exchange String, product String, symbol String, observed_at String
) ENGINE = MergeTree ORDER BY (exchange, product, symbol)
""",
    "instrument_snapshots": """
CREATE TABLE IF NOT EXISTS {db}.instrument_snapshots (
  exchange String, product String, symbol String, observed_at String,
  status Nullable(String), base_asset Nullable(String), quote_asset Nullable(String),
  contract_type Nullable(String), tick_size Nullable(String), step_size Nullable(String),
  min_qty Nullable(String), min_notional Nullable(String), margin_tradable Nullable(UInt8),
  payload_json String
) ENGINE = MergeTree ORDER BY (product, symbol, observed_at)
""",
    "trades": """
CREATE TABLE IF NOT EXISTS {db}.trades (
  exchange String, product String, symbol String, trade_id Int64,
  event_time Nullable(Int64), trade_time Int64, price String, quantity String,
  quote_quantity Nullable(String), buyer_maker UInt8, taker_side String, observed_at String
) ENGINE = MergeTree ORDER BY (product, symbol, trade_id)
""",
    "agg_trades": """
CREATE TABLE IF NOT EXISTS {db}.agg_trades (
  exchange String, product String, symbol String, agg_trade_id Int64,
  first_trade_id Nullable(Int64), last_trade_id Nullable(Int64), price String, quantity String,
  trade_time Int64, event_time Nullable(Int64), buyer_maker UInt8, taker_side String, observed_at String
) ENGINE = MergeTree ORDER BY (product, symbol, agg_trade_id)
""",
    "book_ticker": """
CREATE TABLE IF NOT EXISTS {db}.book_ticker (
  exchange String, product String, symbol String, update_id Nullable(Int64),
  best_bid_price String, best_bid_qty String, best_ask_price String, best_ask_qty String, observed_at String
) ENGINE = MergeTree ORDER BY (product, symbol, observed_at)
""",
    "ticker_24h": """
CREATE TABLE IF NOT EXISTS {db}.ticker_24h (
  exchange String, product String, symbol String,
  price_change Nullable(String), price_change_percent Nullable(String),
  weighted_avg_price Nullable(String), last_price Nullable(String),
  open_price Nullable(String), high_price Nullable(String), low_price Nullable(String),
  base_volume Nullable(String), quote_volume Nullable(String),
  open_time Nullable(Int64), close_time Nullable(Int64), event_time Nullable(Int64),
  first_trade_id Nullable(Int64), last_trade_id Nullable(Int64), trade_count Nullable(Int64),
  observed_at String
) ENGINE = MergeTree ORDER BY (product, symbol, observed_at)
""",
    "candles": """
CREATE TABLE IF NOT EXISTS {db}.candles (
  exchange String, product String, symbol String, interval String,
  open_time Int64, close_time Int64, open String, high String, low String, close String,
  base_volume String, quote_volume String, trade_count Nullable(Int64),
  taker_buy_base_volume Nullable(String), taker_buy_quote_volume Nullable(String),
  is_final UInt8, observed_at String
) ENGINE = MergeTree ORDER BY (exchange, product, symbol, interval, open_time)
""",
    "depth_snapshots": """
CREATE TABLE IF NOT EXISTS {db}.depth_snapshots (
  exchange String, product String, symbol String, last_update_id Int64,
  bids_json String, asks_json String, event_time Nullable(Int64),
  transaction_time Nullable(Int64), observed_at String
) ENGINE = MergeTree ORDER BY (product, symbol, observed_at)
""",
    "depth_updates": """
CREATE TABLE IF NOT EXISTS {db}.depth_updates (
  exchange String, product String, symbol String, first_update_id Int64, final_update_id Int64,
  bids_json String, asks_json String, event_time Nullable(Int64), observed_at String
) ENGINE = MergeTree ORDER BY (product, symbol, final_update_id)
""",
    "funding_rate": """
CREATE TABLE IF NOT EXISTS {db}.funding_rate (
  exchange String, product String, symbol String, funding_rate String, funding_time Int64,
  mark_price Nullable(String), observed_at String
) ENGINE = MergeTree ORDER BY (product, symbol, funding_time)
""",
    "open_interest": """
CREATE TABLE IF NOT EXISTS {db}.open_interest (
  exchange String, product String, symbol String, open_interest String,
  observation_time Nullable(Int64), observed_at String
) ENGINE = MergeTree ORDER BY (product, symbol, observed_at)
""",
    "futures_positioning": """
CREATE TABLE IF NOT EXISTS {db}.futures_positioning (
  exchange String, product String, symbol String, metric String, value String,
  observation_time Nullable(Int64), source_endpoint String, observed_at String, payload_json String
) ENGINE = MergeTree ORDER BY (product, symbol, metric, observed_at)
""",
    "liquidations": """
CREATE TABLE IF NOT EXISTS {db}.liquidations (
  exchange String, product String, symbol String, side String, order_type Nullable(String),
  price String, avg_price Nullable(String), quantity String, order_status Nullable(String),
  event_time Nullable(Int64), observed_at String
) ENGINE = MergeTree ORDER BY (product, symbol, observed_at)
""",
    "mark_price": """
CREATE TABLE IF NOT EXISTS {db}.mark_price (
  exchange String, product String, symbol String, mark_price String,
  index_price Nullable(String), estimated_settle_price Nullable(String),
  funding_rate Nullable(String), next_funding_time Nullable(Int64),
  event_time Nullable(Int64), observed_at String
) ENGINE = MergeTree ORDER BY (product, symbol, observed_at)
""",
    "symbol_coverage": """
CREATE TABLE IF NOT EXISTS {db}.symbol_coverage (
  product String, symbol String, tier String, observed_at String
) ENGINE = MergeTree ORDER BY (product, symbol, observed_at)
""",
    "coverage_history": """
CREATE TABLE IF NOT EXISTS {db}.coverage_history (
  product String, symbol String, feed String, tier String,
  started_at String, ended_at Nullable(String), reason String, close_reason Nullable(String)
) ENGINE = MergeTree ORDER BY (product, symbol, feed, started_at)
""",
    "gap_fill_jobs": """
CREATE TABLE IF NOT EXISTS {db}.gap_fill_jobs (
  product String, symbol String, feed String, gap_start Nullable(Int64), gap_end Nullable(Int64),
  status String, rows_inserted Int64, detail Nullable(String), observed_at String
) ENGINE = MergeTree ORDER BY (product, observed_at)
""",
    "exchange_status": """
CREATE TABLE IF NOT EXISTS {db}.exchange_status (
  exchange String, status_code Nullable(Int64), msg Nullable(String),
  observed_at String, payload_json String
) ENGINE = MergeTree ORDER BY (observed_at)
""",
    "options_mark": """
CREATE TABLE IF NOT EXISTS {db}.options_mark (
  exchange String, product String, symbol String,
  mark_price Nullable(String), mark_iv Nullable(String), bid_iv Nullable(String), ask_iv Nullable(String),
  delta Nullable(String), gamma Nullable(String), theta Nullable(String), vega Nullable(String),
  observed_at String, payload_json String
) ENGINE = MergeTree ORDER BY (product, symbol, observed_at)
""",
    "options_index": """
CREATE TABLE IF NOT EXISTS {db}.options_index (
  exchange String, product String, underlying String, index_price String,
  observation_time Nullable(Int64), observed_at String, payload_json String
) ENGINE = MergeTree ORDER BY (underlying, observed_at)
""",
}


def _tsv_cell(v: Any) -> str:
    if v is None:
        return "\\N"
    s = str(v)
    return s.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n")


def _esc_lit(v: str) -> str:
    return v.replace("\\", "\\\\").replace("'", "\\'")


class ClickHouseSink:
    def __init__(self, cfg: ClickHouseSinkConfig, database: str):
        self._cfg = cfg
        self._db = database
        self._batch_raw: list[str] = []
        self._batch_by_table: dict[str, list[str]] = {t: [] for t in TABLE_DDL}
        self._pending_mutations: list[str] = []
        self._lock = asyncio.Lock()
        self._ensured = False

    def _auth_header(self) -> str:
        token = base64.b64encode(f"{self._cfg.user}:{self._cfg.password}".encode()).decode()
        return f"Basic {token}"

    def _query_sync(self, sql: str, data: bytes | None = None) -> str:
        url = self._cfg.url.rstrip("/") + "/"
        if data is not None:
            url = url + "?" + urllib.parse.urlencode({"query": sql})
            req = urllib.request.Request(url, data=data, method="POST")
            req.add_header("Content-Type", "application/octet-stream")
        else:
            req = urllib.request.Request(url, data=sql.encode("utf-8"), method="POST")
        req.add_header("Authorization", self._auth_header())
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"ClickHouse HTTP {e.code}: {body[:500]}") from e

    async def ensure_schema(self) -> None:
        if self._ensured:
            return

        def _setup() -> None:
            self._query_sync(f"CREATE DATABASE IF NOT EXISTS {self._db}")
            self._query_sync(RAW_DDL.format(db=self._db))
            for ddl in TABLE_DDL.values():
                self._query_sync(ddl.format(db=self._db))

        await asyncio.to_thread(_setup)
        self._ensured = True
        logger.info("ClickHouse schema ready: database=%s", self._db)

    def _raw_line(self, env: Envelope) -> str:
        cells = [
            "binance",
            env.product,
            env.symbol,
            env.stream_name,
            env.source_endpoint,
            resolve_source_type(env),
            env.schema_version,
            env.observed_at,
            env.kind,
            json.dumps(env.payload, separators=(",", ":"), ensure_ascii=False),
        ]
        return "\t".join(_tsv_cell(c) for c in cells)

    def _norm_line(self, env: Envelope) -> tuple[str, str] | None:
        p = env.payload
        kind = env.kind

        if kind == "trade":
            bm = bool(p["buyer_maker"])
            row = [
                "binance", env.product, env.symbol, p["trade_id"], p.get("event_time"),
                p["trade_time"], p["price"], p["quantity"], p.get("quote_quantity"),
                int(bm), taker_side(bm), env.observed_at,
            ]
            return "trades", "\t".join(_tsv_cell(c) for c in row)

        if kind == "agg_trade":
            bm = bool(p["buyer_maker"])
            row = [
                "binance", env.product, env.symbol, p["agg_trade_id"],
                p.get("first_trade_id"), p.get("last_trade_id"), p["price"], p["quantity"],
                p["trade_time"], p.get("event_time"), int(bm), taker_side(bm), env.observed_at,
            ]
            return "agg_trades", "\t".join(_tsv_cell(c) for c in row)

        if kind == "book_ticker":
            row = [
                "binance", env.product, env.symbol, p.get("update_id"),
                p["best_bid_price"], p["best_bid_qty"], p["best_ask_price"], p["best_ask_qty"],
                env.observed_at,
            ]
            return "book_ticker", "\t".join(_tsv_cell(c) for c in row)

        if kind == "ticker_24h":
            row = [
                "binance", env.product, env.symbol,
                p.get("price_change"), p.get("price_change_percent"), p.get("weighted_avg_price"),
                p.get("last_price"), p.get("open_price"), p.get("high_price"), p.get("low_price"),
                p.get("base_volume"), p.get("quote_volume"), p.get("open_time"), p.get("close_time"),
                p.get("event_time"), p.get("first_trade_id"), p.get("last_trade_id"),
                p.get("trade_count"), env.observed_at,
            ]
            return "ticker_24h", "\t".join(_tsv_cell(c) for c in row)

        if kind == "candle":
            row = [
                "binance", env.product, env.symbol, p["interval"], p["open_time"], p["close_time"],
                p["open"], p["high"], p["low"], p["close"], p["base_volume"], p["quote_volume"],
                p.get("trade_count"), p.get("taker_buy_base_volume"), p.get("taker_buy_quote_volume"),
                int(bool(p.get("is_final", False))), env.observed_at,
            ]
            return "candles", "\t".join(_tsv_cell(c) for c in row)

        if kind == "depth_snapshot":
            row = [
                "binance", env.product, env.symbol, p["last_update_id"],
                json.dumps(p["bids"], separators=(",", ":")),
                json.dumps(p["asks"], separators=(",", ":")),
                p.get("event_time"), p.get("transaction_time"), env.observed_at,
            ]
            return "depth_snapshots", "\t".join(_tsv_cell(c) for c in row)

        if kind == "depth_update":
            row = [
                "binance", env.product, env.symbol, p["first_update_id"], p["final_update_id"],
                json.dumps(p["bids"], separators=(",", ":")),
                json.dumps(p["asks"], separators=(",", ":")),
                p.get("event_time"), env.observed_at,
            ]
            return "depth_updates", "\t".join(_tsv_cell(c) for c in row)

        if kind == "instrument_snapshot":
            # Also upsert instruments identity row
            return None  # handled specially in enqueue

        if kind == "funding_rate":
            row = [
                "binance", env.product, env.symbol, p["funding_rate"], p["funding_time"],
                p.get("mark_price"), env.observed_at,
            ]
            return "funding_rate", "\t".join(_tsv_cell(c) for c in row)

        if kind == "open_interest":
            row = [
                "binance", env.product, env.symbol, p["open_interest"],
                p.get("observation_time"), env.observed_at,
            ]
            return "open_interest", "\t".join(_tsv_cell(c) for c in row)

        if kind == "futures_positioning":
            row = [
                "binance", env.product, env.symbol, p["metric"], p["value"],
                p.get("observation_time"), env.source_endpoint, env.observed_at,
                json.dumps(p.get("raw", {}), separators=(",", ":")),
            ]
            return "futures_positioning", "\t".join(_tsv_cell(c) for c in row)

        if kind == "liquidation":
            row = [
                "binance", env.product, env.symbol, p["side"], p.get("order_type"),
                p["price"], p.get("avg_price"), p["quantity"], p.get("order_status"),
                p.get("event_time"), env.observed_at,
            ]
            return "liquidations", "\t".join(_tsv_cell(c) for c in row)

        if kind == "mark_price":
            row = [
                "binance", env.product, env.symbol, p["mark_price"], p.get("index_price"),
                p.get("estimated_settle_price"), p.get("funding_rate"),
                p.get("next_funding_time"), p.get("event_time"), env.observed_at,
            ]
            return "mark_price", "\t".join(_tsv_cell(c) for c in row)

        if kind == "symbol_coverage":
            row = [env.product, env.symbol, p["tier"], env.observed_at]
            return "symbol_coverage", "\t".join(_tsv_cell(c) for c in row)

        if kind == "coverage_history":
            return None  # open insert / close mutation in enqueue

        if kind == "gap_fill_job":
            row = [
                env.product, env.symbol, p["feed"], p.get("gap_start"), p.get("gap_end"),
                p["status"], int(p.get("rows_inserted") or 0), p.get("detail"), env.observed_at,
            ]
            return "gap_fill_jobs", "\t".join(_tsv_cell(c) for c in row)

        if kind == "exchange_status":
            row = [
                "binance", p.get("status"), p.get("msg"), env.observed_at,
                json.dumps(p.get("raw", p), separators=(",", ":")),
            ]
            return "exchange_status", "\t".join(_tsv_cell(c) for c in row)

        if kind == "options_mark":
            row = [
                "binance", env.product, env.symbol, p.get("mark_price"), p.get("mark_iv"),
                p.get("bid_iv"), p.get("ask_iv"), p.get("delta"), p.get("gamma"),
                p.get("theta"), p.get("vega"), env.observed_at,
                json.dumps(p.get("raw", {}), separators=(",", ":")),
            ]
            return "options_mark", "\t".join(_tsv_cell(c) for c in row)

        if kind == "options_index":
            row = [
                "binance", env.product, p["underlying"], p["index_price"],
                p.get("observation_time"), env.observed_at,
                json.dumps(p.get("raw", {}), separators=(",", ":")),
            ]
            return "options_index", "\t".join(_tsv_cell(c) for c in row)

        return None

    def _instrument_lines(self, env: Envelope) -> list[tuple[str, str]]:
        p = env.payload
        inst = [
            "binance", env.product, env.symbol, env.observed_at,
        ]
        snap = [
            "binance", env.product, env.symbol, env.observed_at,
            p.get("status"), p.get("base_asset"), p.get("quote_asset"), p.get("contract_type"),
            p.get("tick_size"), p.get("step_size"), p.get("min_qty"), p.get("min_notional"),
            (int(bool(p.get("margin_tradable", False))) if "margin_tradable" in p else None),
            json.dumps(p, separators=(",", ":")),
        ]
        return [
            ("instruments", "\t".join(_tsv_cell(c) for c in inst)),
            ("instrument_snapshots", "\t".join(_tsv_cell(c) for c in snap)),
        ]

    def _coverage_history_handle(self, env: Envelope) -> tuple[str, str] | str | None:
        """Return (table, line) for open, or mutation SQL string for close."""
        p = env.payload
        action = p.get("action", "open")
        if action == "close":
            ended = _esc_lit(str(p.get("ended_at", env.observed_at)))
            reason = _esc_lit(str(p.get("close_reason") or p.get("reason") or ""))
            product = _esc_lit(env.product)
            symbol = _esc_lit(env.symbol or "")
            feed = _esc_lit(str(p.get("feed", "DEPTH")))
            return (
                f"ALTER TABLE {self._db}.coverage_history UPDATE "
                f"ended_at='{ended}', close_reason='{reason}' "
                f"WHERE product='{product}' AND symbol='{symbol}' AND feed='{feed}' "
                f"AND ended_at IS NULL"
            )
        row = [
            env.product, env.symbol, p.get("feed", "DEPTH"), p["tier"],
            p.get("started_at", env.observed_at), None, p["reason"], None,
        ]
        return "coverage_history", "\t".join(_tsv_cell(c) for c in row)

    async def enqueue(self, env: Envelope) -> None:
        await self.ensure_schema()
        async with self._lock:
            self._batch_raw.append(self._raw_line(env))

            if env.kind == "instrument_snapshot":
                for table, line in self._instrument_lines(env):
                    self._batch_by_table[table].append(line)
            elif env.kind == "coverage_history":
                handled = self._coverage_history_handle(env)
                if isinstance(handled, str):
                    self._pending_mutations.append(handled)
                elif handled is not None:
                    table, line = handled
                    self._batch_by_table[table].append(line)
            else:
                norm = self._norm_line(env)
                if norm is not None:
                    table, line = norm
                    self._batch_by_table[table].append(line)

            if len(self._batch_raw) >= self._cfg.batch_size:
                await self._flush_locked()

    async def flush(self) -> None:
        async with self._lock:
            await self._flush_locked()

    async def _flush_locked(self) -> None:
        raw = self._batch_raw
        by_table = {k: v for k, v in self._batch_by_table.items() if v}
        mutations = self._pending_mutations
        self._batch_raw = []
        self._batch_by_table = {t: [] for t in TABLE_DDL}
        self._pending_mutations = []
        if not raw and not by_table and not mutations:
            return

        def _send() -> None:
            if raw:
                payload = ("\n".join(raw) + "\n").encode("utf-8")
                self._query_sync(
                    f"INSERT INTO {self._db}.raw_events FORMAT TabSeparated",
                    data=payload,
                )
            for table, lines in by_table.items():
                payload = ("\n".join(lines) + "\n").encode("utf-8")
                self._query_sync(
                    f"INSERT INTO {self._db}.{table} FORMAT TabSeparated",
                    data=payload,
                )
            for sql in mutations:
                self._query_sync(sql)

        await asyncio.to_thread(_send)

    async def close(self) -> None:
        await self.flush()
