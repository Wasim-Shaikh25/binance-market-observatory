"""CLI: run the complete data-capture validation checklist against a database.

Usage:
    python -m src.validate [--config config/settings.yaml] [--db PATH] [--out BINANCE_DATA_CAPTURE_REPORT.md]

Without --db, uses the most recently modified database matching the configured path pattern.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from .config import find_latest_db_path, load_settings
from .storage import open_db
from .validation.checks import run_all_checks
from .validation.report import render_report


async def _minmax_obs(conn) -> tuple[str | None, str | None]:
    cur = await conn.execute("SELECT MIN(observed_at), MAX(observed_at) FROM raw_events")
    row = await cur.fetchone()
    return (row[0], row[1]) if row else (None, None)


async def run(config_path: str, out_path: str, db_override: str | None) -> int:
    settings = load_settings(config_path)
    # Prefer smoke config product flags if the DB came from smoke — still load
    # whatever --config the user passed for "enabled?" matrix column.
    db_path = db_override or find_latest_db_path(settings.database_path)
    if db_path is None:
        # Also try smoke path pattern
        db_path = find_latest_db_path("data/market_{run_id}.db")
    if db_path is None:
        print("No database file found. Pass --db.", file=sys.stderr)
        return 1

    # If DB name suggests smoke run, load smoke settings for accurate "enabled" matrix
    cfg_path = config_path
    if "smoke" in db_path.replace("\\", "/").lower() and config_path == "config/settings.yaml":
        from pathlib import Path

        smoke = Path("config/smoke_settings.yaml")
        if smoke.exists():
            cfg_path = str(smoke)
            settings = load_settings(cfg_path)

    conn = await open_db(db_path)
    try:
        results = await run_all_checks(conn, db_path, settings)
        first, last = await _minmax_obs(conn)
    finally:
        await conn.close()

    report = render_report(results, db_path, settings, first, last)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)
    try:
        print(report)
    except UnicodeEncodeError:
        # Windows consoles often can't encode status glyphs; file is UTF-8.
        sys.stdout.buffer.write(report.encode("utf-8", errors="replace"))
        sys.stdout.buffer.write(b"\n")
    print(f"\nWritten to {out_path}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Binance Market Observatory data validation")
    parser.add_argument("--config", default="config/settings.yaml")
    parser.add_argument("--db", default=None)
    parser.add_argument(
        "--out",
        default="validation/report/BINANCE_DATA_CAPTURE_REPORT.md",
        help="Report path (default: validation/report/ per AGENTS.md rule 8)",
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args.config, args.out, args.db)))


if __name__ == "__main__":
    main()
