#!/usr/bin/env python3
"""Compare SQLite vs ClickHouse row counts for a dual-write run.

Usage:
  python validation/script/compare_sqlite_clickhouse.py \\
    --db data/market_<run_id>.db --ch-db bmo_<run_id>
"""

from __future__ import annotations

import argparse
import base64
import sqlite3
import urllib.request


def ch_count(url: str, user: str, password: str, sql: str) -> int:
    auth = base64.b64encode(f"{user}:{password}".encode()).decode()
    req = urllib.request.Request(url.rstrip("/") + "/", data=sql.encode(), method="POST")
    req.add_header("Authorization", f"Basic {auth}")
    return int(urllib.request.urlopen(req, timeout=60).read().decode().strip())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--ch-db", required=True)
    ap.add_argument("--ch-url", default="http://127.0.0.1:8123")
    ap.add_argument("--user", default="default")
    ap.add_argument("--password", default="bench")
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    tables = ["raw_events", "trades", "agg_trades", "book_ticker"]
    print(f"{'table':16} {'sqlite':>12} {'clickhouse':>12} {'delta':>10}")
    for t in tables:
        s = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        try:
            c = ch_count(args.ch_url, args.user, args.password, f"SELECT count() FROM {args.ch_db}.{t}")
        except Exception as exc:  # noqa: BLE001
            print(f"{t:16} {s:12} {'ERR':>12}  {exc}")
            continue
        print(f"{t:16} {s:12} {c:12} {c - s:10}")
    conn.close()
    print("\nNote: ClickHouse MergeTree may keep reconnect duplicates; SQLite UNIQUE ignores them.")
    print("Prefer graceful Ctrl+C shutdown so the last CH batch + archive frame flush.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
