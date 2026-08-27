"""CLI: generate the correctness audit report against an existing database.

Usage:
    python -m src.audit [--config config/settings.yaml] [--out audit_report.md]
"""

from __future__ import annotations

import argparse
import asyncio

from .config import load_settings
from .health import generate_audit_report
from .storage import open_db


async def run(config_path: str, out_path: str) -> None:
    settings = load_settings(config_path)
    conn = await open_db(settings.database_path)
    try:
        report = await generate_audit_report(conn, settings.database_path)
    finally:
        await conn.close()
    with open(out_path, "w") as f:
        f.write(report)
    print(report)
    print(f"\nWritten to {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/settings.yaml")
    parser.add_argument("--out", default="audit_report.md")
    args = parser.parse_args()
    asyncio.run(run(args.config, args.out))


if __name__ == "__main__":
    main()
