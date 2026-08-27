"""Live ClickHouse dual-write sink (HTTP). Batches inserts; best-effort.

Prices/quantities stay String. raw_events.payload_json preserves evidence.
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
from .models import Envelope, resolve_source_type

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

# Minimal normalized mirrors for comparison (exact text decimals).
TABLE_DDL = {
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
}


def _tsv_cell(v: Any) -> str:
    if v is None:
        return "\\N"
    s = str(v)
    return s.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n")


class ClickHouseSink:
    def __init__(self, cfg: ClickHouseSinkConfig, database: str):
        self._cfg = cfg
        self._db = database
        self._batch_raw: list[str] = []
        self._batch_by_table: dict[str, list[str]] = {t: [] for t in TABLE_DDL}
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
        from .models import taker_side

        p = env.payload
        if env.kind == "trade":
            bm = bool(p["buyer_maker"])
            row = [
                "binance",
                env.product,
                env.symbol,
                p["trade_id"],
                p.get("event_time"),
                p["trade_time"],
                p["price"],
                p["quantity"],
                p.get("quote_quantity"),
                int(bm),
                taker_side(bm),
                env.observed_at,
            ]
            return "trades", "\t".join(_tsv_cell(c) for c in row)
        if env.kind == "agg_trade":
            bm = bool(p["buyer_maker"])
            row = [
                "binance",
                env.product,
                env.symbol,
                p["agg_trade_id"],
                p.get("first_trade_id"),
                p.get("last_trade_id"),
                p["price"],
                p["quantity"],
                p["trade_time"],
                p.get("event_time"),
                int(bm),
                taker_side(bm),
                env.observed_at,
            ]
            return "agg_trades", "\t".join(_tsv_cell(c) for c in row)
        if env.kind == "book_ticker":
            row = [
                "binance",
                env.product,
                env.symbol,
                p.get("update_id"),
                p["best_bid_price"],
                p["best_bid_qty"],
                p["best_ask_price"],
                p["best_ask_qty"],
                env.observed_at,
            ]
            return "book_ticker", "\t".join(_tsv_cell(c) for c in row)
        return None

    async def enqueue(self, env: Envelope) -> None:
        await self.ensure_schema()
        async with self._lock:
            self._batch_raw.append(self._raw_line(env))
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
        self._batch_raw = []
        self._batch_by_table = {t: [] for t in TABLE_DDL}
        if not raw and not by_table:
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

        await asyncio.to_thread(_send)

    async def close(self) -> None:
        await self.flush()
