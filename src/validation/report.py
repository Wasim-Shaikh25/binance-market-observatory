"""Render BINANCE_DATA_CAPTURE_REPORT.md from CheckResult list."""

from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import Iterable

from ..config import Settings
from .inventory import FEEDS
from .status import STATUS_GLYPH, CheckResult, Status, combine_status, combine_summary


def _period(results: list[CheckResult]) -> tuple[str, str]:
    for r in results:
        if r.section == "storage" and r.details:
            pass
    return ("(see raw_events MIN/MAX in storage/evidence)", "(see evidence)")


def _product_rollups(results: list[CheckResult]) -> dict[str, Status]:
    buckets: dict[str, list[Status]] = defaultdict(list)
    for r in results:
        if r.section == "products":
            if r.item.startswith("MARGIN"):
                buckets["MARGIN"] = [r.status]
            else:
                buckets[r.item].append(r.status)
    return {k: combine_summary(v) for k, v in buckets.items()}


def _data_type_rollups(results: list[CheckResult]) -> dict[str, Status]:
    mapping = {
        "Trades": ["trades"],
        "AggTrades": ["agg_trades"],
        "BookTicker": ["book_ticker"],
        "Depth": ["depth", "depth_coverage"],
        "Candles": ["candles"],
        "Ticker": ["ticker_24h"],
        "Mark Price": ["mark_price"],
        "Funding": ["funding"],
        "Open Interest": ["open_interest"],
        "Liquidations": ["liquidations"],
        "Positioning Statistics": ["positioning"],
        "Options": ["options"],
        "Instrument Metadata": ["instruments"],
        "Margin Metadata": [],
        "Raw payloads": ["raw_events", "raw_vs_normalized"],
        "Provenance": ["provenance"],
        "Timestamps": ["timestamps"],
        "System health": ["system_health"],
        "Database integrity": ["database", "decimal_precision"],
        "Coverage": ["coverage_matrix"],
        "Reconciliations": ["reconciliation"],
        "Storage": ["storage"],
    }
    out: dict[str, Status] = {}
    for label, sections in mapping.items():
        statuses = [r.status for r in results if r.section in sections]
        if label == "Margin Metadata":
            statuses = [r.status for r in results if r.section == "products" and "MARGIN" in r.item]
        if label == "Options":
            statuses = [r.status for r in results if r.section == "products" and r.item == "OPTIONS"]
            statuses += [r.status for r in results if r.section == "options"]
        if label == "Open Interest":
            statuses += [
                r.status
                for r in results
                if r.section == "options" and r.item == "open_interest"
            ]
        if label == "Depth":
            statuses += [r.status for r in results if r.section == "options" and r.item == "book"]
        out[label] = combine_summary(statuses) if statuses else Status.NOT_IMPLEMENTED
    return out


def render_report(
    results: list[CheckResult],
    db_path: str,
    settings: Settings,
    first_obs: str | None,
    last_obs: str | None,
) -> str:
    now = datetime.now(timezone.utc).isoformat()
    size = os.path.getsize(db_path) if os.path.exists(db_path) else 0
    products = _product_rollups(results)
    data_types = _data_type_rollups(results)

    lines: list[str] = []
    lines.append("========================================")
    lines.append("BINANCE MARKET OBSERVATORY")
    lines.append("DATA CAPTURE AUDIT")
    lines.append("========================================")
    lines.append("")
    lines.append(f"Generated: {now}")
    lines.append(f"Database: `{db_path}` ({size:,} bytes)")
    lines.append(f"Period start (raw_events): {first_obs}")
    lines.append(f"Period end (raw_events): {last_obs}")
    lines.append("")
    lines.append("This report validates **data availability, integrity, timestamps,")
    lines.append("synchronization, provenance, and storage correctness** only.")
    lines.append("It does **not** evaluate profitability, strategies, signals, AI, or market behavior.")
    lines.append("")

    lines.append("========================================")
    lines.append("PRODUCT SUMMARY")
    lines.append("========================================")
    lines.append("")
    for name in ("SPOT", "MARGIN", "USDM_FUTURES", "COINM_FUTURES", "OPTIONS"):
        st = products.get(name, Status.NOT_IMPLEMENTED)
        label = {"MARGIN": "MARGIN METADATA", "USDM_FUTURES": "USDⓈ-M", "COINM_FUTURES": "COIN-M"}.get(name, name)
        lines.append(f"{label}: {STATUS_GLYPH[st]} {st.value}")
    lines.append("")

    lines.append("========================================")
    lines.append("DATA TYPE COVERAGE")
    lines.append("========================================")
    lines.append("")
    for label, st in data_types.items():
        lines.append(f"{label:28} {STATUS_GLYPH[st]} {st.value}")
    lines.append("")

    lines.append("========================================")
    lines.append("VALIDATION MATRIX")
    lines.append("========================================")
    lines.append("")
    lines.append("| Product | Data | Public? | Implemented? | Enabled? | Final | Notes |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in results:
        if r.section != "matrix":
            continue
        d = r.details
        lines.append(
            f"| {r.item.split(' / ')[0]} | {r.item.split(' / ')[1]} | "
            f"{d.get('publicly_available')} | {d.get('implemented')} | {d.get('enabled')} | "
            f"{STATUS_GLYPH[r.status]} {r.status.value} | {r.evidence} |"
        )
    lines.append("")

    lines.append("========================================")
    lines.append("DETAILED CHECKS")
    lines.append("========================================")
    lines.append("")
    by_section: dict[str, list[CheckResult]] = defaultdict(list)
    for r in results:
        if r.section == "matrix":
            continue
        by_section[r.section].append(r)
    for section, items in by_section.items():
        lines.append(f"### {section}")
        lines.append("")
        for r in items:
            lines.append(f"- {r.line()}")
        lines.append("")

    lines.append("========================================")
    lines.append("FIVE QUESTIONS")
    lines.append("========================================")
    lines.append("")
    lines.append("### A. What did we intend to collect?")
    lines.append("")
    lines.append("Per `docs/THESIS.md` / `config/settings.yaml`: Spot, USDS-M, COIN-M public")
    lines.append("market data (trades, aggTrades, bookTicker, ticker, klines, depth top-N,")
    lines.append("instruments+margin metadata, futures mark/funding/OI/liquidations/positioning),")
    lines.append(
        "plus `raw_events`. Options: REST instruments/trades/ticker/mark(IV)/index/"
        "depth/OI when enabled; WS best-effort. Exchange system status polled publicly. "
        "`raw_events.source_type` records websocket vs rest_poll vs rest_backfill."
    )
    lines.append("")
    lines.append("### B. What does Binance actually expose publicly?")
    lines.append("")
    lines.append("See inventory matrix (`publicly_available` column). Based on Binance's")
    lines.append("documented public REST/WS surfaces — not a live docs scrape.")
    lines.append("")
    lines.append("### C. What did our code actually collect?")
    lines.append("")
    lines.append("See product summary + detailed checks against this database file.")
    lines.append(f"Configured products enabled: "
                  f"{[k for k,v in settings.products.items() if v.enabled]}.")
    lines.append("")
    lines.append("### D. How much of it is trustworthy?")
    lines.append("")
    lines.append("Integrity checks: decimal TEXT columns, raw payload JSON samples,")
    lines.append("timestamp separation, duplicate trade IDs, depth resync recording,")
    lines.append("WS/REST system_events, optional trade↔candle and depth↔bookTicker reconciliations.")
    lines.append("Event-driven completeness cannot be proven 100% without exchange reconciliation —")
    lines.append("classify confidence from continuity evidence, not row counts alone.")
    lines.append("")
    lines.append("### E. What are we missing?")
    lines.append("")
    missing = [
        r for r in results
        if r.status in (
            Status.NOT_IMPLEMENTED,
            Status.NOT_PUBLICLY_AVAILABLE,
            Status.FAIL,
            Status.NO_DATA,
            Status.PARTIAL,
        )
        and r.section in ("options", "exchange_wide", "provenance", "products", "candles", "matrix")
    ]
    if not missing:
        lines.append("- (no high-level gaps flagged)")
    else:
        seen = set()
        for r in missing:
            key = (r.section, r.item, r.status)
            if key in seen:
                continue
            seen.add(key)
            lines.append(f"- {STATUS_GLYPH[r.status]} {r.status.value}: {r.section}/{r.item} — {r.evidence}")
    lines.append("")

    lines.append("========================================")
    lines.append("NOTHING-MISSING CHECKLIST")
    lines.append("========================================")
    lines.append("")
    checklist = [
        ("Spot", products.get("SPOT")),
        ("Margin metadata", products.get("MARGIN")),
        ("USDⓈ-M Futures", products.get("USDM_FUTURES")),
        ("COIN-M Futures", products.get("COINM_FUTURES")),
        ("Options", products.get("OPTIONS")),
        ("Instruments", data_types.get("Instrument Metadata")),
        ("Trades", data_types.get("Trades")),
        ("Aggregate trades", data_types.get("AggTrades")),
        ("BookTicker", data_types.get("BookTicker")),
        ("Order book depth", data_types.get("Depth")),
        ("Candles", data_types.get("Candles")),
        ("Ticker", data_types.get("Ticker")),
        ("Mark price", data_types.get("Mark Price")),
        ("Funding", data_types.get("Funding")),
        ("Open interest", data_types.get("Open Interest")),
        ("Liquidations", data_types.get("Liquidations")),
        ("Public positioning", data_types.get("Positioning Statistics")),
        ("Raw payloads", data_types.get("Raw payloads")),
        ("Timestamps", data_types.get("Timestamps")),
        ("System events / health", data_types.get("System health")),
        ("Symbol coverage / tiers", data_types.get("Coverage")),
        ("Database integrity", data_types.get("Database integrity")),
        ("Storage growth", data_types.get("Storage")),
    ]
    for label, st in checklist:
        st = st or Status.NOT_IMPLEMENTED
        box = "x" if st == Status.PASS else " "
        lines.append(f"- [{box}] {label}: {STATUS_GLYPH[st]} {st.value}")
    lines.append("")

    lines.append("## Research-readiness note")
    lines.append("")
    lines.append("Per-symbol research readiness is implied by `symbol_coverage` tiers")
    lines.append("(`BROAD` vs `HIGH_RESOLUTION`) plus the feed matrix above.")
    lines.append("Do **not** treat BROAD symbols as having full depth.")
    lines.append("")
    lines.append("## Final question")
    lines.append("")
    lines.append("> For any supported Binance symbol and timestamp in our collection period,")
    lines.append("> can we tell exactly what public data we captured, what we did not, and why?")
    lines.append("")
    # Honest answer based on coverage tiers + options gap
    has_tiers = any(r.section == "depth_coverage" and r.status == Status.PASS for r in results)
    opts = products.get("OPTIONS", Status.NOT_IMPLEMENTED)
    if has_tiers and opts in (Status.NOT_IMPLEMENTED, Status.NO_DATA):
        lines.append(
            "**Mostly yes** for Spot/USDS-M/COIN-M within configured coverage "
            "(tiers + system_events explain depth gaps). Options: **no** (not implemented). "
            "Full-universe multi-day confidence still requires a long clean run + audit."
        )
    else:
        lines.append("**Partial** — see FAIL/PARTIAL/NOT_IMPLEMENTED items above.")
    lines.append("")
    return "\n".join(lines)
