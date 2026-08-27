#!/usr/bin/env python3
"""Load one observatory SQLite DB into local ClickHouse (Docker) and measure size.

Requires ClickHouse HTTP on http://127.0.0.1:8123 (container bmo-clickhouse).
Keeps prices as strings and raw payload_json so data stays readable evidence.

Usage:
  python research/script/benchmark_clickhouse_load.py --db data/market_….db
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

CH_URL = "http://127.0.0.1:8123/"
CH_USER = "default"
CH_PASSWORD = "bench"
DB_NAME = "bmo_bench"

# Table -> (create SQL without ENGINE, order by, sqlite select)
# Exact decimals remain String.
SPECS = {
    "trades": {
        "order": "(product, symbol, trade_id)",
        "columns": (
            "exchange String, product String, symbol String, trade_id Int64, "
            "event_time Nullable(Int64), trade_time Int64, price String, quantity String, "
            "quote_quantity Nullable(String), buyer_maker UInt8, taker_side String, observed_at String"
        ),
        "sqlite": (
            "SELECT exchange, product, symbol, trade_id, event_time, trade_time, price, quantity, "
            "quote_quantity, buyer_maker, taker_side, observed_at FROM trades"
        ),
    },
    "agg_trades": {
        "order": "(product, symbol, agg_trade_id)",
        "columns": (
            "exchange String, product String, symbol String, agg_trade_id Int64, "
            "first_trade_id Nullable(Int64), last_trade_id Nullable(Int64), price String, quantity String, "
            "trade_time Int64, event_time Nullable(Int64), buyer_maker UInt8, taker_side String, observed_at String"
        ),
        "sqlite": (
            "SELECT exchange, product, symbol, agg_trade_id, first_trade_id, last_trade_id, price, quantity, "
            "trade_time, event_time, buyer_maker, taker_side, observed_at FROM agg_trades"
        ),
    },
    "book_ticker": {
        "order": "(product, symbol, observed_at)",
        "columns": (
            "exchange String, product String, symbol String, update_id Nullable(Int64), "
            "best_bid_price String, best_bid_qty String, best_ask_price String, best_ask_qty String, observed_at String"
        ),
        "sqlite": (
            "SELECT exchange, product, symbol, update_id, best_bid_price, best_bid_qty, "
            "best_ask_price, best_ask_qty, observed_at FROM book_ticker"
        ),
    },
    "candles": {
        "order": "(product, symbol, interval, open_time)",
        "columns": (
            "exchange String, product String, symbol String, interval String, open_time Int64, close_time Int64, "
            "open String, high String, low String, close String, base_volume String, quote_volume String, "
            "trade_count Nullable(Int64), taker_buy_base_volume Nullable(String), "
            "taker_buy_quote_volume Nullable(String), is_final UInt8, observed_at String"
        ),
        "sqlite": (
            "SELECT exchange, product, symbol, interval, open_time, close_time, open, high, low, close, "
            "base_volume, quote_volume, trade_count, taker_buy_base_volume, taker_buy_quote_volume, "
            "is_final, observed_at FROM candles"
        ),
    },
    "depth_updates": {
        "order": "(product, symbol, observed_at)",
        "columns": (
            "exchange String, product String, symbol String, first_update_id Int64, final_update_id Int64, "
            "bids_json String, asks_json String, event_time Nullable(Int64), observed_at String"
        ),
        "sqlite": (
            "SELECT exchange, product, symbol, first_update_id, final_update_id, bids_json, asks_json, "
            "event_time, observed_at FROM depth_updates"
        ),
    },
    "ticker_24h": {
        "order": "(product, symbol, observed_at)",
        "columns": (
            "exchange String, product String, symbol String, price_change Nullable(String), "
            "price_change_percent Nullable(String), weighted_avg_price Nullable(String), last_price Nullable(String), "
            "open_price Nullable(String), high_price Nullable(String), low_price Nullable(String), "
            "base_volume Nullable(String), quote_volume Nullable(String), open_time Nullable(Int64), "
            "close_time Nullable(Int64), event_time Nullable(Int64), first_trade_id Nullable(Int64), "
            "last_trade_id Nullable(Int64), trade_count Nullable(Int64), observed_at String"
        ),
        "sqlite": (
            "SELECT exchange, product, symbol, price_change, price_change_percent, weighted_avg_price, last_price, "
            "open_price, high_price, low_price, base_volume, quote_volume, open_time, close_time, event_time, "
            "first_trade_id, last_trade_id, trade_count, observed_at FROM ticker_24h"
        ),
    },
    "mark_price": {
        "order": "(product, symbol, observed_at)",
        "columns": (
            "exchange String, product String, symbol String, mark_price String, index_price Nullable(String), "
            "estimated_settle_price Nullable(String), funding_rate Nullable(String), "
            "next_funding_time Nullable(Int64), event_time Nullable(Int64), observed_at String"
        ),
        "sqlite": (
            "SELECT exchange, product, symbol, mark_price, index_price, estimated_settle_price, funding_rate, "
            "next_funding_time, event_time, observed_at FROM mark_price"
        ),
    },
    "raw_events": {
        "order": "(product, observed_at)",
        "columns": (
            "exchange String, product String, symbol Nullable(String), stream_name String, "
            "source_endpoint String, schema_version String, observed_at String, payload_json String"
        ),
        "sqlite": (
            "SELECT exchange, product, symbol, stream_name, source_endpoint, schema_version, "
            "observed_at, payload_json FROM raw_events"
        ),
    },
}


def ch_query(sql: str, data: bytes | None = None, timeout: int = 600) -> str:
    import base64

    auth = base64.b64encode(f"{CH_USER}:{CH_PASSWORD}".encode()).decode()
    url = CH_URL + ("?" + urllib.parse.urlencode({"query": sql}) if data is not None else "")
    if data is None:
        req = urllib.request.Request(CH_URL, data=sql.encode("utf-8"), method="POST")
    else:
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/octet-stream")
    req.add_header("Authorization", f"Basic {auth}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"ClickHouse HTTP {e.code}: {body[:800]}") from e


def table_exists_sqlite(conn: sqlite3.Connection, name: str) -> bool:
    return (
        conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
        is not None
    )


def insert_rows(table: str, rows: list[tuple], batch: int = 5000) -> int:
    if not rows:
        return 0
    total = 0
    for i in range(0, len(rows), batch):
        chunk = rows[i : i + batch]
        # JSONEachRow keeps strings readable and avoids TSV escaping issues.
        lines = []
        # column names from first create - use positional via JSON arrays? Better named.
        # We'll use TabSeparated with careful nulls: \N
        buf = []
        for row in chunk:
            parts = []
            for v in row:
                if v is None:
                    parts.append("\\N")
                else:
                    s = str(v).replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n")
                    parts.append(s)
            buf.append("\t".join(parts))
        payload = ("\n".join(buf) + "\n").encode("utf-8")
        ch_query(
            f"INSERT INTO {DB_NAME}.{table} FORMAT TabSeparated",
            data=payload,
        )
        total += len(chunk)
    return total


def mb(n: int | float) -> float:
    return float(n) / (1024 * 1024)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--out-dir", default=None)
    args = ap.parse_args()
    db_path = Path(args.db)
    if not db_path.exists():
        print(f"DB not found: {db_path}", file=sys.stderr)
        return 1

    # ping
    try:
        import base64

        req = urllib.request.Request(CH_URL + "ping")
        req.add_header(
            "Authorization",
            "Basic " + base64.b64encode(f"{CH_USER}:{CH_PASSWORD}".encode()).decode(),
        )
        ping = urllib.request.urlopen(req, timeout=5).read().decode()
    except Exception as exc:  # noqa: BLE001
        print(f"ClickHouse not reachable at {CH_URL}: {exc}", file=sys.stderr)
        print("Start with: docker start bmo-clickhouse (user default / password bench)", file=sys.stderr)
        return 1
    if "Ok" not in ping:
        print(f"Unexpected ping: {ping!r}", file=sys.stderr)
        return 1

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.out_dir) if args.out_dir else Path("research/report") / f"clickhouse_benchmark_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    sqlite_bytes = db_path.stat().st_size
    for suffix in ("-wal", "-shm"):
        p = Path(str(db_path) + suffix)
        if p.exists():
            sqlite_bytes += p.stat().st_size

    ch_query(f"CREATE DATABASE IF NOT EXISTS {DB_NAME}")
    # Fresh load
    for name in SPECS:
        ch_query(f"DROP TABLE IF EXISTS {DB_NAME}.{name}")

    conn = sqlite3.connect(str(db_path))
    first, last, raw_n = conn.execute(
        "SELECT MIN(observed_at), MAX(observed_at), COUNT(*) FROM raw_events"
    ).fetchone()

    loaded: dict[str, int] = {}
    for name, spec in SPECS.items():
        if not table_exists_sqlite(conn, name):
            continue
        ch_query(
            f"CREATE TABLE {DB_NAME}.{name} ({spec['columns']}) "
            f"ENGINE = MergeTree ORDER BY {spec['order']}"
        )
        rows = conn.execute(spec["sqlite"]).fetchall()
        n = insert_rows(name, rows)
        loaded[name] = n
        print(f"loaded {name}: {n}", flush=True)

    conn.close()

    # Force merges for stable size
    for name in loaded:
        ch_query(f"OPTIMIZE TABLE {DB_NAME}.{name} FINAL")

    parts = ch_query(
        "SELECT table, sum(rows), sum(bytes_on_disk), sum(data_compressed_bytes), "
        "sum(data_uncompressed_bytes) "
        f"FROM system.parts WHERE database='{DB_NAME}' AND active "
        "GROUP BY table ORDER BY sum(bytes_on_disk) DESC "
        "FORMAT TabSeparated"
    ).strip()

    table_stats: list[tuple[str, int, int, int, int]] = []
    total_disk = 0
    for line in parts.splitlines():
        if not line.strip():
            continue
        t, rows, disk, comp, uncomp = line.split("\t")
        disk_i = int(disk)
        total_disk += disk_i
        table_stats.append((t, int(rows), disk_i, int(comp), int(uncomp)))

    # Readable sample queries
    samples = {}
    samples["trades_sample"] = ch_query(
        f"SELECT product, symbol, trade_id, price, quantity, taker_side, observed_at "
        f"FROM {DB_NAME}.trades ORDER BY trade_time DESC LIMIT 3 FORMAT PrettyCompact"
    )
    samples["book_count"] = ch_query(
        f"SELECT product, count() AS n FROM {DB_NAME}.book_ticker GROUP BY product "
        f"ORDER BY product FORMAT PrettyCompact"
    )
    samples["raw_payload"] = ch_query(
        f"SELECT product, stream_name, substring(payload_json, 1, 120) AS payload_prefix "
        f"FROM {DB_NAME}.raw_events WHERE product='SPOT' LIMIT 2 FORMAT PrettyCompact"
    )
    samples["trade_price_exact"] = ch_query(
        f"SELECT price, toTypeName(price) FROM {DB_NAME}.trades LIMIT 1 FORMAT PrettyCompact"
    )

    ratio = (sqlite_bytes / total_disk) if total_disk else 0.0
    reduction = (100.0 * (1.0 - total_disk / sqlite_bytes)) if sqlite_bytes else 0.0

    lines = [
        "# ClickHouse readable storage benchmark",
        "",
        f"- Generated (UTC): `{stamp}`",
        f"- Source DB: `{db_path.as_posix()}`",
        f"- Period: `{first}` -> `{last}`",
        f"- raw_events rows (SQLite): **{raw_n:,}**",
        f"- ClickHouse HTTP: `{CH_URL}` database `{DB_NAME}`",
        "",
        "## Size comparison",
        "",
        "| Store | Size (MiB) | Notes |",
        "|---|---:|---|",
        f"| SQLite (db+wal+shm) | {mb(sqlite_bytes):.2f} | Current collector |",
        f"| **ClickHouse (active parts)** | **{mb(total_disk):.2f}** | MergeTree on disk, includes raw_events |",
        "",
        f"- ClickHouse is **{ratio:.2f}x** smaller than this SQLite file "
        f"(**{reduction:.1f}%** fewer bytes).",
        "- Prices remain **String** (exact decimal text), payloads remain **readable JSON strings**.",
        "",
        "## ClickHouse per-table disk",
        "",
        "| Table | Rows | bytes_on_disk (MiB) | compressed (MiB) | uncompressed (MiB) |",
        "|---|---:|---:|---:|---:|",
    ]
    for t, rows, disk, comp, uncomp in table_stats:
        lines.append(
            f"| {t} | {rows:,} | {mb(disk):.3f} | {mb(comp):.3f} | {mb(uncomp):.3f} |"
        )

    lines += [
        "",
        "## Loaded row counts",
        "",
        "| Table | Rows loaded |",
        "|---|---:|",
    ]
    for t, n in sorted(loaded.items()):
        lines.append(f"| {t} | {n:,} |")

    lines += [
        "",
        "## Readability checks (live SELECT)",
        "",
        "### Latest trades",
        "```",
        samples["trades_sample"].rstrip(),
        "```",
        "",
        "### book_ticker counts by product",
        "```",
        samples["book_count"].rstrip(),
        "```",
        "",
        "### Raw payload still readable (prefix)",
        "```",
        samples["raw_payload"].rstrip(),
        "```",
        "",
        "### Price type stays exact text",
        "```",
        samples["trade_price_exact"].rstrip(),
        "```",
        "",
        "## Ops notes",
        "",
        "- Container: `docker start|stop bmo-clickhouse`",
        "- This benchmark does **not** switch the live collector off SQLite.",
        "- Fair long-term design remains: compressed raw archive + ClickHouse hot + Parquet cold.",
        "",
    ]
    report = out_dir / "REPORT.md"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    sys.stdout.buffer.write(report.read_bytes())
    print(f"\nWrote {report}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
