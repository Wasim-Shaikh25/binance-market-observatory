#!/usr/bin/env python3
"""Benchmark one observatory SQLite DB vs raw NDJSON and Parquet+ZSTD.

Does not migrate the collector. Requires: pyarrow (optional but needed for Parquet).
ClickHouse is reported only if `clickhouse-client` exists.

Usage:
  python research/script/benchmark_storage_formats.py --db data/market_….db
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


TABLES = (
    "trades",
    "agg_trades",
    "book_ticker",
    "candles",
    "depth_updates",
    "ticker_24h",
    "mark_price",
)


def _mb(n: int) -> float:
    return n / (1024 * 1024)


def _size(path: Path) -> int:
    return path.stat().st_size if path.exists() else 0


def export_raw_ndjson(conn: sqlite3.Connection, out_path: Path) -> tuple[int, int]:
    n = 0
    with out_path.open("w", encoding="utf-8", newline="\n") as f:
        for (payload,) in conn.execute("SELECT payload_json FROM raw_events"):
            f.write(payload if payload.endswith("\n") else payload + "\n")
            n += 1
    gz_path = out_path.with_suffix(out_path.suffix + ".gz")
    with out_path.open("rb") as src, gzip.open(gz_path, "wb", compresslevel=6) as dst:
        shutil.copyfileobj(src, dst)
    return n, _size(gz_path)


def export_parquet_tables(conn: sqlite3.Connection, out_dir: Path) -> dict[str, int]:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError:
        print("pyarrow not installed — skip Parquet exports", file=sys.stderr)
        return {}

    sizes: dict[str, int] = {}
    for table in TABLES:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        if not exists:
            continue
        cur = conn.execute(f"SELECT * FROM {table}")
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        if not rows:
            continue
        # Build column-oriented arrays (all as string/int as returned by sqlite)
        arrays = {c: [r[i] for r in rows] for i, c in enumerate(cols)}
        arrow_table = pa.table(arrays)
        path = out_dir / f"{table}.parquet"
        pq.write_table(arrow_table, path, compression="zstd", compression_level=3)
        sizes[table] = _size(path)
    return sizes


def export_raw_events_parquet(conn: sqlite3.Connection, out_dir: Path) -> int:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError:
        return 0
    cols_avail = {r[1] for r in conn.execute("PRAGMA table_info(raw_events)")}
    select_cols = [
        c
        for c in (
            "product",
            "symbol",
            "stream_name",
            "source_endpoint",
            "source_type",
            "schema_version",
            "observed_at",
            "payload_json",
        )
        if c in cols_avail
    ]
    if "payload_json" not in select_cols:
        return 0
    sql = "SELECT " + ", ".join(select_cols) + " FROM raw_events"
    cur = conn.execute(sql)
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    if not rows:
        return 0
    arrays = {c: [r[i] for r in rows] for i, c in enumerate(cols)}
    path = out_dir / "raw_events.parquet"
    pq.write_table(pa.table(arrays), path, compression="zstd", compression_level=3)
    return _size(path)


def clickhouse_available() -> bool:
    return shutil.which("clickhouse-client") is not None or shutil.which("clickhouse") is not None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="Path to one market_*.db file")
    ap.add_argument(
        "--out-dir",
        default=None,
        help="Output directory (default research/report/storage_benchmark_<stamp>)",
    )
    args = ap.parse_args()
    db_path = Path(args.db)
    if not db_path.exists():
        print(f"DB not found: {db_path}", file=sys.stderr)
        return 1

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.out_dir) if args.out_dir else Path("research/report") / f"storage_benchmark_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "artifacts").mkdir(exist_ok=True)

    sqlite_bytes = _size(db_path) + _size(Path(str(db_path) + "-wal")) + _size(Path(str(db_path) + "-shm"))
    conn = sqlite3.connect(str(db_path))
    first, last, raw_n = conn.execute(
        "SELECT MIN(observed_at), MAX(observed_at), COUNT(*) FROM raw_events"
    ).fetchone()

    ndjson_path = out_dir / "artifacts" / "raw_events.ndjson"
    raw_rows, gz_bytes = export_raw_ndjson(conn, ndjson_path)
    ndjson_bytes = _size(ndjson_path)

    parquet_dir = out_dir / "artifacts" / "parquet"
    parquet_dir.mkdir(exist_ok=True)
    table_sizes = export_parquet_tables(conn, parquet_dir)
    parquet_norm = sum(table_sizes.values())
    raw_parquet = export_raw_events_parquet(conn, parquet_dir)

    conn.close()

    # Optional: delete huge uncompressed ndjson to save disk; keep .gz
    try:
        ndjson_path.unlink()
    except OSError:
        pass

    ch = clickhouse_available()
    lines = [
        "# Storage format benchmark (one DB file)",
        "",
        f"- Generated (UTC): `{stamp}`",
        f"- Source DB: `{db_path.as_posix()}`",
        f"- Period: `{first}` -> `{last}`",
        f"- raw_events rows: **{raw_n:,}**",
        "",
        "## Sizes",
        "",
        "| Representation | Size (MiB) | Notes |",
        "|---|---:|---|",
        f"| SQLite (db+wal+shm) | {_mb(sqlite_bytes):.2f} | Current collector store (raw+normalized+indexes) |",
        f"| Raw NDJSON (payloads only) | {_mb(ndjson_bytes):.2f} | Uncompressed wire-ish JSON lines ({raw_rows:,} lines) |",
        f"| Raw NDJSON + gzip | {_mb(gz_bytes):.2f} | Same payloads, gzip -6 |",
        f"| Parquet+ZSTD (normalized tables) | {_mb(parquet_norm):.2f} | {', '.join(table_sizes) or 'none'} |",
        f"| Parquet+ZSTD (raw_events incl. payload_json) | {_mb(raw_parquet):.2f} | Evidence column retained |",
        f"| ClickHouse | {'N/A' if not ch else 'see local install'} | {'Not installed on this host' if not ch else 'client found'} |",
        "",
        "## Ratios vs SQLite",
        "",
    ]
    if sqlite_bytes:
        for label, nbytes in (
            ("raw NDJSON", ndjson_bytes),
            ("raw NDJSON+gzip", gz_bytes),
            ("Parquet normalized", parquet_norm),
            ("Parquet raw_events", raw_parquet),
            ("Parquet norm + raw_events", parquet_norm + raw_parquet),
        ):
            if nbytes:
                ratio = sqlite_bytes / nbytes
                reduction = 100.0 * (1.0 - nbytes / sqlite_bytes)
                lines.append(
                    f"- **{label}**: {ratio:.2f}x smaller footprint than SQLite "
                    f"({reduction:.1f}% less bytes than the SQLite file)"
                )
    lines += [
        "",
        "## Per-table Parquet+ZSTD",
        "",
    ]
    if table_sizes:
        lines.append("| Table | MiB |")
        lines.append("|---|---:|")
        for t, s in sorted(table_sizes.items(), key=lambda x: -x[1]):
            lines.append(f"| {t} | {_mb(s):.3f} |")
    else:
        lines.append("_No Parquet tables written (install pyarrow)._")

    lines += [
        "",
        "## Interpretation",
        "",
        "- SQLite holds **raw + normalized + indexes** in one file — that is why it can",
        "  look large vs a single Parquet of typed columns alone.",
        "- A fair 'same evidence' archive is roughly **gzipped raw NDJSON** (or",
        "  Parquet of `raw_events`) **plus** Parquet of normalized tables — not",
        "  Parquet-normalized alone.",
        "- ClickHouse was **not** measured here (no server/client). Install and re-run",
        "  after the planned multi-hour capture if you want a CH number.",
        "- This does **not** change the live collector. Migration stays: measure → decide.",
        "",
        "## Artifacts",
        "",
        f"- `{ (out_dir / 'artifacts').as_posix() }/`",
        "",
    ]
    report = out_dir / "REPORT.md"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    sys.stdout.buffer.write(report.read_bytes())
    print(f"\nWrote {report}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
