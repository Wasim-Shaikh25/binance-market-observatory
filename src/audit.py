"""CLI: generate the correctness audit report against an existing database.

Usage:
    python -m src.audit [--config config/settings.yaml] [--db path/to/run.db] [--out audit_report.md]

Without --db, targets the most recently modified database file matching the
configured path pattern (see docs/requirements/2026-08-27-per-run-db-and-
background-run-scripts/) -- i.e. "the run I just did."
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from .config import find_latest_db_path, load_settings
from .health import generate_audit_report
from .storage import open_db


async def run(config_path: str, out_path: str, db_override: str | None = None) -> None:
    settings = load_settings(config_path)
    db_path = db_override or find_latest_db_path(settings.database_path)
    if db_path is None:
        print(
            f"No database file found matching pattern {settings.database_path!r}. "
            "Has the collector been run yet? Pass --db to target a specific file.",
            file=sys.stderr,
        )
        sys.exit(1)

    conn = await open_db(db_path)
    try:
        report = await generate_audit_report(conn, db_path)
    finally:
        await conn.close()
    with open(out_path, "w") as f:
        f.write(report)
    print(f"Auditing: {db_path}\n")
    print(report)
    print(f"\nWritten to {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/settings.yaml")
    parser.add_argument("--db", default=None, help="Explicit database file (default: most recent run)")
    parser.add_argument(
        "--out",
        default="validation/report/audit_report.md",
        help="Report path (default: validation/report/ per AGENTS.md rule 8)",
    )
    args = parser.parse_args()
    asyncio.run(run(args.config, args.out, args.db))


if __name__ == "__main__":
    main()
