"""Correctness audit report -- answers "did we actually capture the market",
not "does the database contain rows" (docs/THESIS.md #8). Run with
`python -m src.audit` against a running or completed collection database.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import aiosqlite

METRIC_EVENT_TYPES = ("ws_connected", "ws_reconnect", "depth_resync", "rest_failure", "db_write_failure")


async def _scalar(conn: aiosqlite.Connection, sql: str, params: tuple = ()) -> int:
    cur = await conn.execute(sql, params)
    row = await cur.fetchone()
    return row[0] if row and row[0] is not None else 0


async def generate_audit_report(conn: aiosqlite.Connection, db_path: str, stale_after_minutes: int = 10) -> str:
    lines: list[str] = []
    now = datetime.now(timezone.utc)
    lines.append(f"# Collector Audit Report\n\nGenerated: {now.isoformat()}\n")

    lines.append("## Symbol coverage\n")
    cur = await conn.execute("SELECT product, COUNT(DISTINCT symbol) FROM raw_events WHERE symbol IS NOT NULL GROUP BY product")
    rows = await cur.fetchall()
    if not rows:
        lines.append("No data collected yet.\n")
    for product, count in rows:
        lines.append(f"- {product}: {count} distinct symbols observed")
    lines.append("")

    lines.append("## Event counts by product / stream kind\n")
    cur = await conn.execute(
        "SELECT product, stream_name, COUNT(*) FROM raw_events GROUP BY product, stream_name ORDER BY product, COUNT(*) DESC"
    )
    rows = await cur.fetchall()
    for product, stream_name, count in rows[:200]:
        lines.append(f"- {product} / `{stream_name}`: {count}")
    lines.append("")

    lines.append("## Duplicate / dropped writes\n")
    cur = await conn.execute("SELECT product, COUNT(*) FROM raw_events WHERE stream_name LIKE '%@trade' GROUP BY product")
    raw_trade_counts = dict(await cur.fetchall())
    cur = await conn.execute("SELECT product, COUNT(*) FROM trades GROUP BY product")
    normalized_trade_counts = dict(await cur.fetchall())
    for product, raw_count in raw_trade_counts.items():
        normalized = normalized_trade_counts.get(product, 0)
        lines.append(f"- {product}: {raw_count} raw trade events vs {normalized} normalized rows (diff = duplicates or failed writes: {raw_count - normalized})")
    lines.append("")

    lines.append("## Depth resyncs (update-ID gaps detected)\n")
    cur = await conn.execute(
        "SELECT product, symbol, COUNT(*) FROM system_events WHERE event_type='depth_resync' GROUP BY product, symbol ORDER BY COUNT(*) DESC"
    )
    rows = await cur.fetchall()
    if not rows:
        lines.append("No resyncs recorded.\n")
    for product, symbol, count in rows[:100]:
        lines.append(f"- {product} {symbol}: {count} resyncs")
    lines.append("")

    lines.append("## WebSocket reconnects\n")
    for event_type in ("ws_connected", "ws_reconnect"):
        count = await _scalar(conn, "SELECT COUNT(*) FROM system_events WHERE event_type=?", (event_type,))
        lines.append(f"- {event_type}: {count}")
    lines.append("")

    lines.append("## REST failures\n")
    count = await _scalar(conn, "SELECT COUNT(*) FROM system_events WHERE event_type='rest_failure'")
    lines.append(f"- rest_failure: {count}\n")

    lines.append("## Database write failures\n")
    count = await _scalar(conn, "SELECT COUNT(*) FROM system_events WHERE event_type='db_write_failure'")
    lines.append(f"- db_write_failure: {count}\n")

    lines.append("## Stale streams (no raw event in the last "
                  f"{stale_after_minutes} minutes)\n")
    cutoff = (now - timedelta(minutes=stale_after_minutes)).isoformat()
    cur = await conn.execute(
        "SELECT product, symbol, MAX(observed_at) FROM raw_events WHERE symbol IS NOT NULL "
        "GROUP BY product, symbol HAVING MAX(observed_at) < ?",
        (cutoff,),
    )
    rows = await cur.fetchall()
    if not rows:
        lines.append("None.\n")
    for product, symbol, last_seen in rows[:100]:
        lines.append(f"- {product} {symbol}: last seen {last_seen}")
    lines.append("")

    lines.append("## Coverage tiers (latest assignment per symbol)\n")
    cur = await conn.execute(
        """
        SELECT product, tier, COUNT(*) FROM (
            SELECT product, symbol, tier,
                   ROW_NUMBER() OVER (PARTITION BY product, symbol ORDER BY id DESC) AS rn
            FROM symbol_coverage
        ) WHERE rn = 1
        GROUP BY product, tier ORDER BY product, tier
        """
    )
    rows = await cur.fetchall()
    if not rows:
        lines.append("No coverage-tier data yet.\n")
    for product, tier, count in rows:
        lines.append(f"- {product} {tier}: {count} symbols")
    lines.append("")

    lines.append("## Futures positioning data\n")
    cur = await conn.execute(
        "SELECT product, metric, COUNT(DISTINCT symbol), COUNT(*) FROM futures_positioning "
        "GROUP BY product, metric ORDER BY product, metric"
    )
    rows = await cur.fetchall()
    if not rows:
        lines.append("No positioning data yet (disabled, not yet due to poll, or the endpoint is failing -- check REST failures above).\n")
    for product, metric, symbols, count in rows:
        lines.append(f"- {product} / {metric}: {count} observations across {symbols} symbols")
    lines.append("")

    lines.append("## Storage\n")
    for suffix in ("", "-wal", "-shm"):
        p = db_path + suffix
        if os.path.exists(p):
            lines.append(f"- {os.path.basename(p)}: {os.path.getsize(p):,} bytes")
    lines.append("")

    return "\n".join(lines)
