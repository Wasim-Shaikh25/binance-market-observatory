"""Run the data-capture validation checklist; write report under validation/report/.

Usage (from repo root):
    python validation/script/run_validation.py [--db PATH] [--config PATH]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.validate import run  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/settings.yaml")
    parser.add_argument("--db", default=None)
    parser.add_argument(
        "--out",
        default=str(ROOT / "validation" / "report" / "BINANCE_DATA_CAPTURE_REPORT.md"),
    )
    args = parser.parse_args()
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    raise SystemExit(asyncio.run(run(args.config, args.out, args.db)))


if __name__ == "__main__":
    main()
