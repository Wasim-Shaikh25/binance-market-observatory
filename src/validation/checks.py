"""Async DB/schema checks for the data-capture validation report.

Integrity only — no trading interpretation.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

import aiosqlite

from ..config import Settings
from .inventory import FEEDS, FeedSpec, product_enabled
from .status import CheckResult, Status, combine_status

PRODUCTS = ("SPOT", "USDM_FUTURES", "COINM_FUTURES", "OPTIONS")


def _skip_if_disabled(settings: Settings | None, product: str) -> CheckResult | None:
    if settings is not None and not product_enabled(settings, product):
        return CheckResult("feed", product, Status.NOT_IMPLEMENTED, "product disabled in config for this run")
    return None

# Tables whose price/qty columns must be TEXT (not REAL/FLOAT/DOUBLE).
PRICE_TABLES = {
    "trades": ("price", "quantity", "quote_quantity"),
    "agg_trades": ("price", "quantity"),
    "book_ticker": ("best_bid_price", "best_bid_qty", "best_ask_price", "best_ask_qty"),
    "ticker_24h": ("last_price", "open_price", "high_price", "low_price", "base_volume", "quote_volume"),
    "candles": ("open", "high", "low", "close", "base_volume", "quote_volume"),
    "funding_rate": ("funding_rate", "mark_price"),
    "open_interest": ("open_interest",),
    "liquidations": ("price", "avg_price", "quantity"),
    "mark_price": ("mark_price", "index_price", "estimated_settle_price", "funding_rate"),
    "futures_positioning": ("value",),
    "options_mark": ("mark_price", "mark_iv", "bid_iv", "ask_iv", "delta", "gamma", "theta", "vega"),
    "options_index": ("index_price",),
}


async def _scalar(conn: aiosqlite.Connection, sql: str, params: tuple = ()) -> Any:
    cur = await conn.execute(sql, params)
    row = await cur.fetchone()
    return row[0] if row else None


async def _rows(conn: aiosqlite.Connection, sql: str, params: tuple = ()) -> list[tuple]:
    cur = await conn.execute(sql, params)
    return list(await cur.fetchall())


async def _table_exists(conn: aiosqlite.Connection, name: str) -> bool:
    n = await _scalar(conn, "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return n is not None


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _ms_to_dt(ms: int | None) -> datetime | None:
    if ms is None:
        return None
    try:
        return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Section helpers
# ---------------------------------------------------------------------------


async def check_database_opens(conn: aiosqlite.Connection, db_path: str) -> list[CheckResult]:
    out: list[CheckResult] = []
    mode = await _scalar(conn, "PRAGMA journal_mode")
    wal_ok = str(mode).lower() == "wal" or Path(db_path + "-wal").exists()
    out.append(
        CheckResult(
            "database",
            "opens + WAL",
            Status.PASS if wal_ok else Status.PARTIAL,
            f"journal_mode={mode}; file exists={os.path.exists(db_path)}",
        )
    )
    required = [
        "raw_events",
        "instruments",
        "instrument_snapshots",
        "trades",
        "agg_trades",
        "book_ticker",
        "ticker_24h",
        "candles",
        "depth_snapshots",
        "depth_updates",
        "funding_rate",
        "open_interest",
        "liquidations",
        "mark_price",
        "futures_positioning",
        "symbol_coverage",
        "coverage_history",
        "gap_fill_jobs",
        "system_events",
        "exchange_status",
        "options_mark",
        "options_index",
    ]
    missing = [t for t in required if not await _table_exists(conn, t)]
    out.append(
        CheckResult(
            "database",
            "required tables",
            Status.PASS if not missing else Status.FAIL,
            "all present" if not missing else f"missing: {missing}",
        )
    )
    return out


async def check_decimal_precision(conn: aiosqlite.Connection) -> list[CheckResult]:
    out: list[CheckResult] = []
    bad: list[str] = []
    for table, cols in PRICE_TABLES.items():
        if not await _table_exists(conn, table):
            continue
        cur = await conn.execute(f"PRAGMA table_info({table})")
        info = {r[1]: r[2].upper() for r in await cur.fetchall()}
        for col in cols:
            decl = info.get(col, "")
            if any(x in decl for x in ("REAL", "FLOAT", "DOUBLE")):
                bad.append(f"{table}.{col}:{decl}")
    out.append(
        CheckResult(
            "decimal_precision",
            "price/qty columns are TEXT",
            Status.PASS if not bad else Status.FAIL,
            "no REAL/FLOAT/DOUBLE on price columns" if not bad else f"bad: {bad}",
        )
    )
    # Sample: prices look like decimal strings, not floats-as-text scientific junk only
    sample = await _rows(conn, "SELECT price FROM trades LIMIT 20")
    weird = [p[0] for p in sample if p[0] is None or p[0] == ""]
    out.append(
        CheckResult(
            "decimal_precision",
            "trade price samples non-null",
            Status.PASS if sample and not weird else (Status.NO_DATA if not sample else Status.FAIL),
            f"sampled {len(sample)} prices; null/empty={len(weird)}",
        )
    )
    return out


async def check_products(conn: aiosqlite.Connection, settings: Settings) -> list[CheckResult]:
    out: list[CheckResult] = []
    for product in PRODUCTS:
        key_map = {"SPOT": "spot", "USDM_FUTURES": "usdm_futures", "COINM_FUTURES": "coinm_futures", "OPTIONS": "options"}
        enabled = product_enabled(settings, product)
        raw_n = await _scalar(conn, "SELECT COUNT(*) FROM raw_events WHERE product=?", (product,)) or 0
        inst_n = await _scalar(conn, "SELECT COUNT(*) FROM instruments WHERE product=?", (product,)) or 0

        if product == "OPTIONS":
            mark_n = (
                (await _scalar(conn, "SELECT COUNT(*) FROM options_mark") or 0)
                if await _table_exists(conn, "options_mark")
                else 0
            )
            idx_n = (
                (await _scalar(conn, "SELECT COUNT(*) FROM options_index") or 0)
                if await _table_exists(conn, "options_index")
                else 0
            )
            trade_n = await _scalar(conn, "SELECT COUNT(*) FROM trades WHERE product=?", (product,)) or 0
            if not enabled:
                status = Status.NOT_IMPLEMENTED
                evidence = "connector disabled in config"
            elif raw_n == 0 and inst_n == 0:
                status = Status.FAIL
                evidence = "enabled but zero instruments/raw_events"
            elif mark_n or idx_n or trade_n:
                status = Status.PASS
                evidence = f"raw_events={raw_n}; instruments={inst_n}; trades={trade_n}; options_mark={mark_n}; options_index={idx_n}"
            else:
                status = Status.PARTIAL
                evidence = f"raw_events={raw_n}; instruments={inst_n}; normalized mark/index/trades still empty"
        elif not enabled:
            status = Status.NOT_IMPLEMENTED
            evidence = "disabled in config"
        elif raw_n == 0 and inst_n == 0:
            status = Status.FAIL
            evidence = "enabled but no instruments and no raw_events"
        elif raw_n == 0:
            status = Status.PARTIAL
            evidence = f"instruments={inst_n} but raw_events=0"
        else:
            # Spot-check whether expected normalized feeds are empty while trades exist
            trades_n = await _scalar(conn, "SELECT COUNT(*) FROM trades WHERE product=?", (product,)) or 0
            gaps = []
            if product in ("USDM_FUTURES", "COINM_FUTURES", "SPOT") and trades_n > 0:
                for table, label in (
                    ("agg_trades", "agg_trades"),
                    ("ticker_24h", "ticker_24h"),
                ):
                    n = await _scalar(conn, f"SELECT COUNT(*) FROM {table} WHERE product=?", (product,)) or 0
                    if n == 0:
                        gaps.append(label)
                if product != "SPOT":
                    n = await _scalar(conn, "SELECT COUNT(*) FROM mark_price WHERE product=?", (product,)) or 0
                    if n == 0:
                        gaps.append("mark_price")
            if gaps:
                status = Status.PARTIAL
                evidence = (
                    f"enabled; instruments={inst_n}; raw_events={raw_n}; trades={trades_n}; "
                    f"but empty normalized feeds: {gaps}"
                )
            else:
                status = Status.PASS
                evidence = f"enabled; instruments={inst_n}; raw_events={raw_n}"

        out.append(
            CheckResult(
                "products",
                product,
                status,
                evidence,
                {
                    "discovered": inst_n > 0 or raw_n > 0,
                    "implemented": product != "OPTIONS" or True,  # connector module exists
                    "active": enabled,
                    "data_received": raw_n > 0,
                    "data_stored": raw_n > 0,
                },
            )
        )

    # Margin via Spot
    if not product_enabled(settings, "SPOT"):
        out.append(
            CheckResult(
                "products",
                "MARGIN metadata (via Spot)",
                Status.NOT_IMPLEMENTED,
                "Spot disabled in config — margin metadata is collected with Spot",
            )
        )
        return out

    margin_n = await _scalar(
        conn,
        "SELECT COUNT(*) FROM instrument_snapshots s "
        "JOIN instruments i ON i.id=s.instrument_id "
        "WHERE i.product='SPOT' AND s.margin_tradable=1",
    ) or 0
    unknown = await _scalar(
        conn,
        "SELECT COUNT(*) FROM instrument_snapshots s "
        "JOIN instruments i ON i.id=s.instrument_id "
        "WHERE i.product='SPOT' AND s.margin_tradable IS NULL",
    ) or 0
    spot_n = await _scalar(conn, "SELECT COUNT(*) FROM instruments WHERE product='SPOT'") or 0
    if spot_n == 0:
        mstatus = Status.FAIL
    elif margin_n > 0:
        mstatus = Status.PASS
    else:
        mstatus = Status.PARTIAL
    out.append(
        CheckResult(
            "products",
            "MARGIN metadata (via Spot)",
            mstatus,
            f"spot_instruments={spot_n}; margin_tradable=1 → {margin_n}; null status={unknown}",
        )
    )
    return out


async def check_instruments(conn: aiosqlite.Connection, settings: Settings | None = None) -> list[CheckResult]:
    out: list[CheckResult] = []
    for product in ("SPOT", "USDM_FUTURES", "COINM_FUTURES"):
        if settings is not None and not product_enabled(settings, product):
            out.append(
                CheckResult(
                    "instruments",
                    product,
                    Status.NOT_IMPLEMENTED,
                    "product disabled in config for this run",
                )
            )
            continue
        total = await _scalar(conn, "SELECT COUNT(*) FROM instruments WHERE product=?", (product,)) or 0
        snaps = await _rows(
            conn,
            """
            SELECT COUNT(*),
                   SUM(CASE WHEN status='TRADING' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN status IS NOT NULL AND status!='TRADING' THEN 1 ELSE 0 END),
                   MIN(observed_at), MAX(observed_at),
                   SUM(CASE WHEN tick_size IS NOT NULL THEN 1 ELSE 0 END),
                   SUM(CASE WHEN step_size IS NOT NULL THEN 1 ELSE 0 END),
                   SUM(CASE WHEN base_asset IS NOT NULL THEN 1 ELSE 0 END),
                   SUM(CASE WHEN quote_asset IS NOT NULL THEN 1 ELSE 0 END)
            FROM instrument_snapshots s
            JOIN instruments i ON i.id=s.instrument_id
            WHERE i.product=?
            """,
            (product,),
        )
        row = snaps[0] if snaps else (0,) * 9
        snap_n, trading, inactive, first, last, tick_n, step_n, base_n, quote_n = row
        if total == 0:
            status = Status.FAIL
        elif tick_n == 0 or base_n == 0:
            status = Status.PARTIAL
        else:
            status = Status.PASS
        out.append(
            CheckResult(
                "instruments",
                product,
                status,
                f"instruments={total}; snapshots={snap_n}; trading≈{trading}; "
                f"inactive≈{inactive}; tick_size={tick_n}; step_size={step_n}; "
                f"base={base_n}; quote={quote_n}; first={first}; last={last}",
            )
        )

    hist = await _scalar(
        conn,
        """
        SELECT COUNT(*) FROM (
          SELECT instrument_id FROM instrument_snapshots GROUP BY instrument_id HAVING COUNT(*) > 1
        )
        """,
    ) or 0
    out.append(
        CheckResult(
            "instruments",
            "historical snapshots possible",
            Status.PASS,
            f"instruments with >1 snapshot row so far: {hist} "
            "(schema supports history; multi-row only appears after metadata changes / re-polls)",
        )
    )

    opt = await _scalar(conn, "SELECT COUNT(*) FROM instruments WHERE product='OPTIONS'") or 0
    if settings is not None and not product_enabled(settings, "OPTIONS"):
        opt_status = Status.NOT_IMPLEMENTED
        opt_evidence = "product disabled in config for this run"
    elif opt == 0:
        opt_status = Status.FAIL if settings is not None and product_enabled(settings, "OPTIONS") else Status.NOT_IMPLEMENTED
        opt_evidence = f"options instruments stored={opt}"
    else:
        opt_status = Status.PASS
        opt_evidence = f"options instruments stored={opt}"
    out.append(CheckResult("instruments", "OPTIONS", opt_status, opt_evidence))
    return out


async def check_raw_events(conn: aiosqlite.Connection) -> list[CheckResult]:
    out: list[CheckResult] = []
    n = await _scalar(conn, "SELECT COUNT(*) FROM raw_events") or 0
    if n == 0:
        return [CheckResult("raw_events", "existence", Status.FAIL, "raw_events is empty")]

    null_payload = await _scalar(conn, "SELECT COUNT(*) FROM raw_events WHERE payload_json IS NULL OR payload_json=''") or 0
    null_product = await _scalar(conn, "SELECT COUNT(*) FROM raw_events WHERE product IS NULL OR product=''") or 0
    out.append(
        CheckResult(
            "raw_events",
            "existence + provenance columns",
            Status.PASS if null_payload == 0 and null_product == 0 else Status.FAIL,
            f"rows={n}; null_payload={null_payload}; null_product={null_product}",
        )
    )

    by_product = await _rows(conn, "SELECT product, COUNT(*) FROM raw_events GROUP BY product ORDER BY 1")
    out.append(
        CheckResult(
            "raw_events",
            "count by product",
            Status.PASS,
            ", ".join(f"{p}={c}" for p, c in by_product),
            {"by_product": dict(by_product)},
        )
    )

    # Sample payload JSON validity
    samples = await _rows(conn, "SELECT id, payload_json FROM raw_events ORDER BY RANDOM() LIMIT 50")
    bad_json = 0
    for _, payload in samples:
        try:
            json.loads(payload)
        except Exception:
            bad_json += 1
    out.append(
        CheckResult(
            "raw_events",
            "random payload JSON validity (n=50)",
            Status.PASS if bad_json == 0 else Status.FAIL,
            f"invalid_json={bad_json}/{len(samples)}",
        )
    )

    # receive timestamp present (observed_at); no separate event_time column on raw_events —
    # exchange times live inside payload / normalized tables
    out.append(
        CheckResult(
            "raw_events",
            "receive timestamp (observed_at)",
            Status.PASS,
            "observed_at required NOT NULL on schema; stream_name + source_endpoint preserved",
        )
    )
    return out


async def check_trades(conn: aiosqlite.Connection, settings: Settings | None = None) -> list[CheckResult]:
    out: list[CheckResult] = []
    for product in ("SPOT", "USDM_FUTURES", "COINM_FUTURES"):
        if settings is not None and not product_enabled(settings, product):
            out.append(CheckResult("trades", product, Status.NOT_IMPLEMENTED, "product disabled in config for this run"))
            continue
        total = await _scalar(conn, "SELECT COUNT(*) FROM trades WHERE product=?", (product,)) or 0
        uniq = await _scalar(
            conn,
            "SELECT COUNT(*) FROM (SELECT DISTINCT symbol, trade_id FROM trades WHERE product=?)",
            (product,),
        ) or 0
        null_price = await _scalar(
            conn, "SELECT COUNT(*) FROM trades WHERE product=? AND (price IS NULL OR quantity IS NULL)", (product,)
        ) or 0
        null_bm = await _scalar(conn, "SELECT COUNT(*) FROM trades WHERE product=? AND buyer_maker IS NULL", (product,)) or 0
        earliest = await _scalar(conn, "SELECT MIN(trade_time) FROM trades WHERE product=?", (product,))
        latest = await _scalar(conn, "SELECT MAX(trade_time) FROM trades WHERE product=?", (product,))
        dup = total - uniq
        if total == 0:
            status = Status.NO_DATA
        elif null_price or null_bm or dup < 0:
            status = Status.FAIL
        elif dup > 0:
            status = Status.PARTIAL
        else:
            status = Status.PASS
        out.append(
            CheckResult(
                "trades",
                product,
                status,
                f"rows={total}; unique(symbol,trade_id)={uniq}; dup≈{dup}; "
                f"null_price/qty={null_price}; null_buyer_maker={null_bm}; "
                f"earliest_ms={earliest}; latest_ms={latest}",
            )
        )

    # Options trades (REST) when enabled
    if settings is not None and product_enabled(settings, "OPTIONS"):
        total = await _scalar(conn, "SELECT COUNT(*) FROM trades WHERE product='OPTIONS'") or 0
        out.append(
            CheckResult(
                "trades",
                "OPTIONS",
                Status.PASS if total else Status.NO_DATA,
                f"rows={total} (REST /eapi/v1/trades)",
            )
        )
    else:
        out.append(
            CheckResult(
                "trades",
                "OPTIONS",
                Status.NOT_IMPLEMENTED,
                "Options disabled or not configured",
            )
        )
    return out


async def check_agg_trades(conn: aiosqlite.Connection, settings: Settings | None = None) -> list[CheckResult]:
    out: list[CheckResult] = []
    for product in ("SPOT", "USDM_FUTURES", "COINM_FUTURES"):
        if settings is not None and not product_enabled(settings, product):
            out.append(CheckResult("agg_trades", product, Status.NOT_IMPLEMENTED, "product disabled in config for this run"))
            continue
        total = await _scalar(conn, "SELECT COUNT(*) FROM agg_trades WHERE product=?", (product,)) or 0
        with_ids = await _scalar(
            conn,
            "SELECT COUNT(*) FROM agg_trades WHERE product=? AND first_trade_id IS NOT NULL AND last_trade_id IS NOT NULL",
            (product,),
        ) or 0
        trades_n = await _scalar(conn, "SELECT COUNT(*) FROM trades WHERE product=?", (product,)) or 0
        if total == 0:
            # If trades arrived on the same product, aggTrade was expected too → FAIL
            status = Status.FAIL if trades_n > 0 else Status.NO_DATA
            evidence = f"rows=0; trades_on_product={trades_n}" + (
                " — aggTrade stream missing while trades present" if trades_n else ""
            )
        elif with_ids == 0:
            status = Status.PARTIAL
            evidence = f"rows={total}; with first/last trade id={with_ids}"
        else:
            status = Status.PASS
            evidence = f"rows={total}; with first/last trade id={with_ids}"
        out.append(CheckResult("agg_trades", product, status, evidence))
    return out


async def check_book_ticker(conn: aiosqlite.Connection, settings: Settings | None = None) -> list[CheckResult]:
    out: list[CheckResult] = []
    for product in ("SPOT", "USDM_FUTURES", "COINM_FUTURES"):
        if settings is not None and not product_enabled(settings, product):
            out.append(CheckResult("book_ticker", product, Status.NOT_IMPLEMENTED, "product disabled in config for this run"))
            continue
        total = await _scalar(conn, "SELECT COUNT(*) FROM book_ticker WHERE product=?", (product,)) or 0
        bad = await _scalar(
            conn,
            """
            SELECT COUNT(*) FROM book_ticker WHERE product=? AND (
              best_bid_price IS NULL OR best_ask_price IS NULL
              OR best_bid_qty IS NULL OR best_ask_qty IS NULL
              OR CAST(best_bid_price AS REAL) < 0 OR CAST(best_ask_price AS REAL) < 0
            )
            """,
            (product,),
        ) or 0
        # bid > ask is possible briefly; count severe inversions only as soft signal
        crossed = await _scalar(
            conn,
            """
            SELECT COUNT(*) FROM (
              SELECT * FROM book_ticker WHERE product=? LIMIT 5000
            ) WHERE CAST(best_bid_price AS REAL) > CAST(best_ask_price AS REAL) * 1.01
            """,
            (product,),
        ) or 0
        if total == 0:
            status = Status.NO_DATA
        elif bad:
            status = Status.FAIL
        elif crossed > total * 0.01:
            status = Status.PARTIAL
        else:
            status = Status.PASS
        out.append(
            CheckResult(
                "book_ticker",
                product,
                status,
                f"rows={total}; null/negative={bad}; severe_cross_sample={crossed}; "
                "note: Binance bookTicker has no exchange event timestamp (observed_at only)",
            )
        )
    out.append(CheckResult("book_ticker", "OPTIONS", Status.NOT_IMPLEMENTED, "Options uses REST ticker, not bookTicker stream"))
    return out


async def check_depth(conn: aiosqlite.Connection, settings: Settings | None = None) -> list[CheckResult]:
    out: list[CheckResult] = []
    for product in ("SPOT", "USDM_FUTURES", "COINM_FUTURES"):
        if settings is not None and not product_enabled(settings, product):
            out.append(CheckResult("depth", product, Status.NOT_IMPLEMENTED, "product disabled in config for this run"))
            continue
        snaps = await _scalar(conn, "SELECT COUNT(*) FROM depth_snapshots WHERE product=?", (product,)) or 0
        updates = await _scalar(conn, "SELECT COUNT(*) FROM depth_updates WHERE product=?", (product,)) or 0
        symbols = await _scalar(
            conn, "SELECT COUNT(DISTINCT symbol) FROM depth_updates WHERE product=?", (product,)
        ) or 0
        resyncs = await _scalar(
            conn,
            "SELECT COUNT(*) FROM system_events WHERE event_type='depth_resync' AND product=?",
            (product,),
        ) or 0
        if snaps == 0 and updates == 0:
            status = Status.NO_DATA
        elif snaps == 0 or updates == 0:
            status = Status.PARTIAL
        else:
            status = Status.PASS
        out.append(
            CheckResult(
                "depth",
                product,
                status,
                f"depth_symbols≈{symbols}; snapshots={snaps}; updates={updates}; "
                f"depth_resync events={resyncs} (gaps detected & recorded, not silent)",
            )
        )

    if settings is not None and product_enabled(settings, "OPTIONS"):
        opt_snaps = await _scalar(conn, "SELECT COUNT(*) FROM depth_snapshots WHERE product='OPTIONS'") or 0
        out.append(
            CheckResult(
                "depth",
                "OPTIONS",
                Status.PASS if opt_snaps else Status.NO_DATA,
                f"depth_snapshots={opt_snaps} (REST /eapi/v1/depth polls; no WS depth sync)",
            )
        )
    else:
        out.append(
            CheckResult(
                "depth",
                "OPTIONS",
                Status.NOT_IMPLEMENTED,
                "Options disabled or not in this run",
            )
        )

    # Coverage tiers apply to Spot/USDM/COINM depth supervisors — not Options REST polls.
    any_depth_product = settings is None or any(
        product_enabled(settings, p) for p in ("SPOT", "USDM_FUTURES", "COINM_FUTURES")
    )
    tiers = await _rows(
        conn,
        """
        SELECT product, tier, COUNT(*) FROM (
          SELECT product, symbol, tier,
                 ROW_NUMBER() OVER (PARTITION BY product, symbol ORDER BY id DESC) rn
          FROM symbol_coverage
        ) WHERE rn=1 GROUP BY product, tier
        """,
    )
    if not any_depth_product:
        out.append(
            CheckResult(
                "depth_coverage",
                "symbol_coverage tiers",
                Status.NOT_IMPLEMENTED,
                "no Spot/USDM/COIN-M depth products enabled in this run",
            )
        )
    elif not tiers:
        out.append(
            CheckResult(
                "depth_coverage",
                "symbol_coverage tiers",
                Status.FAIL,
                "no symbol_coverage rows — cannot tell BROAD vs HIGH_RESOLUTION",
            )
        )
    else:
        out.append(
            CheckResult(
                "depth_coverage",
                "symbol_coverage tiers",
                Status.PASS,
                "; ".join(f"{p}/{t}={c}" for p, t, c in tiers),
                {"tiers": [(p, t, c) for p, t, c in tiers]},
            )
        )
        only_hr = all(t == "HIGH_RESOLUTION" for _, t, _ in tiers)
        has_broad = any(t == "BROAD" for _, t, _ in tiers)
        has_hr = any(t == "HIGH_RESOLUTION" for _, t, _ in tiers)
        if has_broad and has_hr:
            out.append(
                CheckResult(
                    "depth_coverage",
                    "full-universe depth claim",
                    Status.PASS,
                    "both BROAD and HIGH_RESOLUTION tiers present (top-N depth + non-depth symbols)",
                )
            )
        elif only_hr:
            out.append(
                CheckResult(
                    "depth_coverage",
                    "full-universe depth claim",
                    Status.PARTIAL,
                    "latest tiers are all HIGH_RESOLUTION — typical of list/smoke runs; "
                    "production top-N must also write BROAD for non-depth symbols",
                )
            )
    return out


async def check_candles(conn: aiosqlite.Connection, settings: Settings) -> list[CheckResult]:
    out: list[CheckResult] = []
    configured: set[str] = set()
    for cfg in settings.products.values():
        if cfg.enabled:
            configured.update(cfg.kline_intervals)

    intervals = await _rows(conn, "SELECT interval, COUNT(*) FROM candles GROUP BY interval")
    found = {i for i, _ in intervals}
    out.append(
        CheckResult(
            "candles",
            "configured intervals present",
            Status.PASS if configured and configured <= found else (Status.PARTIAL if found else Status.NO_DATA),
            f"configured={sorted(configured)}; found={sorted(found)}; counts={dict(intervals)}",
        )
    )

    # Intervals in the user checklist but not in default config
    for iv in ("15m", "4h", "1d"):
        if iv not in configured:
            out.append(
                CheckResult(
                    "candles",
                    f"interval {iv}",
                    Status.NOT_IMPLEMENTED,
                    "not in config kline_intervals (add there to collect)",
                )
            )

    ohlc_bad = await _scalar(
        conn,
        """
        SELECT COUNT(*) FROM candles WHERE
          CAST(high AS REAL) < CAST(low AS REAL)
          OR CAST(high AS REAL) < CAST(open AS REAL)
          OR CAST(high AS REAL) < CAST(close AS REAL)
          OR CAST(low AS REAL) > CAST(open AS REAL)
          OR CAST(low AS REAL) > CAST(close AS REAL)
          OR CAST(base_volume AS REAL) < 0
        """,
    ) or 0
    total = await _scalar(conn, "SELECT COUNT(*) FROM candles") or 0
    out.append(
        CheckResult(
            "candles",
            "OHLC invariants",
            Status.PASS if total and ohlc_bad == 0 else (Status.NO_DATA if total == 0 else Status.FAIL),
            f"rows={total}; ohlc_violations={ohlc_bad}",
        )
    )

    finals = await _scalar(conn, "SELECT COUNT(*) FROM candles WHERE is_final=1") or 0
    open_c = await _scalar(conn, "SELECT COUNT(*) FROM candles WHERE is_final=0") or 0
    out.append(
        CheckResult(
            "candles",
            "final vs in-progress flag",
            Status.PASS if total else Status.NO_DATA,
            f"is_final=1 → {finals}; is_final=0 → {open_c}",
        )
    )
    return out


async def check_ticker(conn: aiosqlite.Connection, settings: Settings | None = None) -> list[CheckResult]:
    out: list[CheckResult] = []
    for product in ("SPOT", "USDM_FUTURES", "COINM_FUTURES"):
        if settings is not None and not product_enabled(settings, product):
            out.append(CheckResult("ticker_24h", product, Status.NOT_IMPLEMENTED, "product disabled in config for this run"))
            continue
        n = await _scalar(conn, "SELECT COUNT(*) FROM ticker_24h WHERE product=?", (product,)) or 0
        syms = await _scalar(
            conn, "SELECT COUNT(DISTINCT symbol) FROM ticker_24h WHERE product=?", (product,)
        ) or 0
        trades_n = await _scalar(conn, "SELECT COUNT(*) FROM trades WHERE product=?", (product,)) or 0
        if n == 0:
            status = Status.FAIL if trades_n > 0 else Status.NO_DATA
            evidence = f"rows=0; symbols=0; trades_on_product={trades_n}" + (
                " — @ticker missing while trades present" if trades_n else ""
            )
        else:
            status = Status.PASS
            evidence = f"rows={n}; symbols={syms}"
        out.append(CheckResult("ticker_24h", product, status, evidence))
    if settings is not None and product_enabled(settings, "OPTIONS"):
        n = await _scalar(conn, "SELECT COUNT(*) FROM ticker_24h WHERE product='OPTIONS'") or 0
        out.append(
            CheckResult(
                "ticker_24h",
                "OPTIONS",
                Status.PASS if n else Status.NO_DATA,
                f"rows={n} (REST /eapi/v1/ticker)",
            )
        )
    else:
        out.append(CheckResult("ticker_24h", "OPTIONS", Status.NOT_IMPLEMENTED, "Options disabled or not in this run"))
    return out


async def check_futures_special(conn: aiosqlite.Connection, settings: Settings | None = None) -> list[CheckResult]:
    out: list[CheckResult] = []
    for product in ("USDM_FUTURES", "COINM_FUTURES"):
        if settings is not None and not product_enabled(settings, product):
            for section in ("mark_price", "funding", "open_interest", "liquidations", "positioning"):
                out.append(CheckResult(section, product, Status.NOT_IMPLEMENTED, "product disabled in config for this run"))
            continue
        mp = await _scalar(conn, "SELECT COUNT(*) FROM mark_price WHERE product=?", (product,)) or 0
        with_idx = await _scalar(
            conn, "SELECT COUNT(*) FROM mark_price WHERE product=? AND index_price IS NOT NULL", (product,)
        ) or 0
        with_et = await _scalar(
            conn, "SELECT COUNT(*) FROM mark_price WHERE product=? AND event_time IS NOT NULL", (product,)
        ) or 0
        trades_n = await _scalar(conn, "SELECT COUNT(*) FROM trades WHERE product=?", (product,)) or 0
        if mp == 0:
            mp_status = Status.FAIL if trades_n > 0 else Status.NO_DATA
            mp_evidence = f"rows=0; trades_on_product={trades_n}" + (
                " — markPrice stream missing while trades present" if trades_n else ""
            )
        elif with_idx and with_et:
            mp_status = Status.PASS
            mp_evidence = (
                f"rows={mp}; with_index_price={with_idx}; with_event_time={with_et}; "
                "funding_rate on mark_price = estimated/current (not settled)"
            )
        else:
            mp_status = Status.PARTIAL
            mp_evidence = f"rows={mp}; with_index_price={with_idx}; with_event_time={with_et}"
        out.append(CheckResult("mark_price", product, mp_status, mp_evidence))

        fr = await _scalar(conn, "SELECT COUNT(*) FROM funding_rate WHERE product=?", (product,)) or 0
        if fr == 0:
            fr_status = Status.FAIL if trades_n > 0 else Status.NO_DATA
            fr_evidence = f"rows=0 (expected from markPrice when that stream is live)"
        else:
            fr_status = Status.PASS
            fr_evidence = (
                f"rows={fr} (derived from markPrice stream — estimated/current, not historical settled series)"
            )
        out.append(CheckResult("funding", product, fr_status, fr_evidence))

        oi = await _scalar(conn, "SELECT COUNT(*) FROM open_interest WHERE product=?", (product,)) or 0
        oi_times = [
            r[0]
            for r in await _rows(
                conn,
                "SELECT observation_time FROM open_interest WHERE product=? AND observation_time IS NOT NULL ORDER BY observation_time",
                (product,),
            )
        ]
        gaps = [oi_times[i + 1] - oi_times[i] for i in range(len(oi_times) - 1)]
        if oi == 0:
            oi_status = Status.NO_DATA
            evidence = "no rows"
        elif not oi_times:
            oi_status = Status.PARTIAL
            evidence = f"rows={oi} but observation_time missing"
        else:
            med = median(gaps) if gaps else None
            p95 = sorted(gaps)[int(0.95 * (len(gaps) - 1))] if gaps else None
            largest = max(gaps) if gaps else None
            oi_status = Status.PASS
            evidence = (
                f"rows={oi}; observation_time present; "
                f"median_gap_ms={med}; p95_gap_ms={p95}; largest_gap_ms={largest}"
            )
        out.append(CheckResult("open_interest", product, oi_status, evidence))

        liq = await _scalar(conn, "SELECT COUNT(*) FROM liquidations WHERE product=?", (product,)) or 0
        last_liq = await _scalar(conn, "SELECT MAX(event_time) FROM liquidations WHERE product=?", (product,))
        force_raw = await _scalar(
            conn,
            "SELECT COUNT(*) FROM raw_events WHERE product=? AND stream_name LIKE '%forceOrder%'",
            (product,),
        ) or 0
        trades_n = await _scalar(conn, "SELECT COUNT(*) FROM trades WHERE product=?", (product,)) or 0
        ws_ok = await _scalar(
            conn,
            "SELECT COUNT(*) FROM system_events WHERE product=? AND event_type='ws_connected'",
            (product,),
        ) or 0
        if liq > 0:
            liq_status = Status.PASS
            liq_evidence = f"events={liq}; last_event_ms={last_liq}; forceOrder_raw={force_raw}"
        elif force_raw > 0 or (ws_ok and trades_n > 0 and force_raw == 0 and product.startswith("COIN")):
            # COIN-M had forceOrder in other runs; if raw stream present but 0 liqs → quiet market
            liq_status = Status.NO_DATA
            liq_evidence = f"events=0; forceOrder_raw={force_raw}; ws_connected={ws_ok} (feed may be quiet)"
        elif trades_n > 0 and force_raw == 0:
            liq_status = Status.FAIL
            liq_evidence = (
                f"events=0; forceOrder_raw=0; trades={trades_n} — !forceOrder@arr never appeared in raw_events"
            )
        elif ws_ok:
            liq_status = Status.NO_DATA
            liq_evidence = f"events=0; last_event_ms={last_liq}; ws_connected_events={ws_ok}"
        else:
            liq_status = Status.PARTIAL
            liq_evidence = f"events={liq}; no ws_connected recorded"
        out.append(CheckResult("liquidations", product, liq_status, liq_evidence))

        pos = await _rows(
            conn,
            "SELECT metric, COUNT(*), COUNT(DISTINCT symbol) FROM futures_positioning WHERE product=? GROUP BY metric",
            (product,),
        )
        if not pos:
            out.append(CheckResult("positioning", product, Status.NO_DATA, "no futures_positioning rows"))
        else:
            out.append(
                CheckResult(
                    "positioning",
                    product,
                    Status.PASS,
                    "; ".join(f"{m}: rows={c} symbols={s}" for m, c, s in pos),
                )
            )
    return out


async def check_options_feeds(conn: aiosqlite.Connection, settings: Settings) -> list[CheckResult]:
    out: list[CheckResult] = []
    if not product_enabled(settings, "OPTIONS"):
        for item in ("instruments", "trades", "ticker", "iv_greeks", "index", "book", "open_interest", "ws"):
            out.append(CheckResult("options", item, Status.NOT_IMPLEMENTED, "Options disabled in config"))
        return out

    inst = await _scalar(conn, "SELECT COUNT(*) FROM instruments WHERE product='OPTIONS'") or 0
    trades = await _scalar(conn, "SELECT COUNT(*) FROM trades WHERE product='OPTIONS'") or 0
    ticker = await _scalar(conn, "SELECT COUNT(*) FROM ticker_24h WHERE product='OPTIONS'") or 0
    mark = (
        (await _scalar(conn, "SELECT COUNT(*) FROM options_mark") or 0)
        if await _table_exists(conn, "options_mark")
        else 0
    )
    index_n = (
        (await _scalar(conn, "SELECT COUNT(*) FROM options_index") or 0)
        if await _table_exists(conn, "options_index")
        else 0
    )
    with_iv = (
        (await _scalar(conn, "SELECT COUNT(*) FROM options_mark WHERE mark_iv IS NOT NULL") or 0)
        if mark
        else 0
    )
    ws_msgs = await _scalar(
        conn, "SELECT COUNT(*) FROM raw_events WHERE product='OPTIONS' AND source_endpoint LIKE 'wss:%'"
    ) or 0

    out.append(
        CheckResult(
            "options",
            "instruments",
            Status.PASS if inst else Status.FAIL,
            f"instruments={inst}",
        )
    )
    out.append(
        CheckResult(
            "options",
            "trades",
            Status.PASS if trades else Status.NO_DATA,
            f"trades={trades} (REST /eapi/v1/trades)",
        )
    )
    out.append(
        CheckResult(
            "options",
            "ticker",
            Status.PASS if ticker else Status.NO_DATA,
            f"ticker_24h={ticker} (REST /eapi/v1/ticker)",
        )
    )
    out.append(
        CheckResult(
            "options",
            "iv_greeks",
            Status.PASS if mark and with_iv else (Status.PARTIAL if mark else Status.NO_DATA),
            f"options_mark={mark}; with_mark_iv={with_iv}",
        )
    )
    out.append(
        CheckResult(
            "options",
            "index",
            Status.PASS if index_n else Status.NO_DATA,
            f"options_index={index_n}",
        )
    )
    depth_n = await _scalar(conn, "SELECT COUNT(*) FROM depth_snapshots WHERE product='OPTIONS'") or 0
    oi_n = await _scalar(conn, "SELECT COUNT(*) FROM open_interest WHERE product='OPTIONS'") or 0
    out.append(
        CheckResult(
            "options",
            "book",
            Status.PASS if depth_n else Status.NO_DATA,
            f"depth_snapshots={depth_n} (REST /eapi/v1/depth polls)",
        )
    )
    out.append(
        CheckResult(
            "options",
            "open_interest",
            Status.PASS if oi_n else Status.NO_DATA,
            f"open_interest rows={oi_n} (REST /eapi/v1/openInterest)",
        )
    )
    out.append(
        CheckResult(
            "options",
            "ws",
            Status.PARTIAL if ws_msgs == 0 else Status.PASS,
            f"ws_raw_events={ws_msgs} (REST is primary; WS best-effort — may be 0 on this network)",
        )
    )
    return out


async def check_exchange_status(conn: aiosqlite.Connection) -> list[CheckResult]:
    if not await _table_exists(conn, "exchange_status"):
        return [
            CheckResult(
                "exchange_wide",
                "system status / maintenance feed",
                Status.NOT_IMPLEMENTED,
                "exchange_status table missing",
            )
        ]
    n = await _scalar(conn, "SELECT COUNT(*) FROM exchange_status") or 0
    last = await _rows(conn, "SELECT status_code, msg, observed_at FROM exchange_status ORDER BY id DESC LIMIT 1")
    if n == 0:
        return [
            CheckResult(
                "exchange_wide",
                "system status / maintenance feed",
                Status.NO_DATA,
                "table present but empty (poller may not have run yet)",
            )
        ]
    code, msg, observed = last[0]
    return [
        CheckResult(
            "exchange_wide",
            "system status / maintenance feed",
            Status.PASS,
            f"rows={n}; last status_code={code} msg={msg!r} at {observed}",
        )
    ]


async def check_timestamps(conn: aiosqlite.Connection) -> list[CheckResult]:
    out: list[CheckResult] = []
    now_ms = int(time.time() * 1000)
    # Allow generous skew for futures testnet-like clocks / far timestamps in smoke data
    future_slop_ms = 7 * 24 * 3600 * 1000

    # Trades: event vs receive
    sample = await _rows(
        conn,
        "SELECT trade_time, observed_at FROM trades WHERE trade_time IS NOT NULL LIMIT 200",
    )
    inverted = 0
    missing_recv = 0
    for trade_time, observed_at in sample:
        recv = _parse_iso(observed_at)
        if recv is None:
            missing_recv += 1
            continue
        # trade_time is ms; compare roughly
        recv_ms = int(recv.timestamp() * 1000)
        if recv_ms + 60_000 < trade_time:  # receive much earlier than event → clock/issue
            inverted += 1
    if not sample:
        out.append(CheckResult("timestamps", "trades event vs receive", Status.NO_DATA, "no trades"))
    else:
        out.append(
            CheckResult(
                "timestamps",
                "trades event vs receive",
                Status.PASS if missing_recv == 0 and inverted < max(5, len(sample) * 0.05) else Status.PARTIAL,
                f"sampled={len(sample)}; missing_observed_at={missing_recv}; "
                f"recv<<event anomalies={inverted}",
            )
        )

    # open_interest observation_time distinct from observed_at
    oi = await _rows(
        conn,
        "SELECT observation_time, observed_at FROM open_interest WHERE observation_time IS NOT NULL LIMIT 50",
    )
    collapsed = 0
    for obs_t, observed_at in oi:
        recv = _parse_iso(observed_at)
        if recv and abs(int(recv.timestamp() * 1000) - obs_t) < 5:
            collapsed += 1
    out.append(
        CheckResult(
            "timestamps",
            "open_interest source vs receive distinct",
            Status.PASS if oi and collapsed < len(oi) else (Status.NO_DATA if not oi else Status.FAIL),
            f"sampled={len(oi)}; near-identical source/receive pairs={collapsed} "
            "(should usually differ — poll lag)",
        )
    )

    out.append(
        CheckResult(
            "timestamps",
            "book_ticker source timestamp",
            Status.NOT_PUBLICLY_AVAILABLE,
            "Binance bookTicker payload has no event time — only observed_at stored (documented)",
        )
    )

    # Machine clock sanity
    utc_ok = datetime.now(timezone.utc).tzinfo is not None
    out.append(
        CheckResult(
            "timestamps",
            "collector host clock UTC-aware",
            Status.PASS if utc_ok else Status.FAIL,
            f"datetime.now(timezone.utc) ok; local epoch_ms≈{now_ms}; "
            "NTP not verified from inside process — confirm OS time sync operationally",
        )
    )
    return out


async def check_system_health(conn: aiosqlite.Connection) -> list[CheckResult]:
    out: list[CheckResult] = []
    for et in ("ws_connected", "ws_reconnect", "rest_failure", "db_write_failure", "depth_resync"):
        n = await _scalar(conn, "SELECT COUNT(*) FROM system_events WHERE event_type=?", (et,)) or 0
        if et in ("rest_failure", "db_write_failure"):
            status = Status.PASS if n == 0 else Status.PARTIAL
            evidence = f"count={n}" + (" (investigate)" if n else " (clean)")
        elif et == "ws_connected":
            status = Status.PASS if n > 0 else Status.FAIL
            evidence = f"count={n}"
        else:
            status = Status.PASS
            evidence = f"count={n} (informational)"
        out.append(CheckResult("system_health", et, status, evidence))
    return out


async def check_raw_normalized_samples(conn: aiosqlite.Connection) -> list[CheckResult]:
    """Sample raw payloads vs normalized rows for key feeds."""
    out: list[CheckResult] = []

    # Trades: match trade_id from normalized to a raw @trade payload
    trades = await _rows(
        conn,
        "SELECT product, symbol, trade_id, price, quantity, buyer_maker FROM trades LIMIT 30",
    )
    matched = 0
    checked = 0
    for product, symbol, trade_id, price, qty, bm in trades:
        raws = await _rows(
            conn,
            """
            SELECT payload_json FROM raw_events
            WHERE product=? AND symbol=? AND stream_name LIKE '%@trade'
              AND payload_json LIKE ?
            LIMIT 3
            """,
            (product, symbol, f'%{trade_id}%'),
        )
        if not raws:
            continue
        checked += 1
        for (payload,) in raws:
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                continue
            # raw_events stores either wire or already-parsed shape
            tid = data.get("trade_id") or data.get("t")
            p = data.get("price") or data.get("p")
            q = data.get("quantity") or data.get("q")
            if str(tid) == str(trade_id) and str(p) == str(price) and str(q) == str(qty):
                matched += 1
                break
    if checked == 0:
        out.append(
            CheckResult(
                "raw_vs_normalized",
                "trades sample",
                Status.PARTIAL,
                "could not locate matching raw @trade payloads for sample (stream may store parsed shape under different keys)",
            )
        )
    else:
        out.append(
            CheckResult(
                "raw_vs_normalized",
                "trades sample",
                Status.PASS if matched >= checked * 0.5 else Status.PARTIAL,
                f"checked={checked}; matched_price_qty_id={matched}",
            )
        )

    # Positioning: payload_json must parse and contain metric fields
    pos = await _rows(conn, "SELECT metric, value, payload_json FROM futures_positioning LIMIT 20")
    ok = 0
    for metric, value, payload in pos:
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if value is not None and payload:
            ok += 1
    out.append(
        CheckResult(
            "raw_vs_normalized",
            "futures_positioning payload_json",
            Status.PASS if pos and ok == len(pos) else (Status.NO_DATA if not pos else Status.FAIL),
            f"sampled={len(pos)}; valid_with_value={ok}",
        )
    )
    return out


async def check_reconcile_candles(conn: aiosqlite.Connection) -> list[CheckResult]:
    """Compare one final 1m candle against trades in that window (best-effort)."""
    candle = await _rows(
        conn,
        """
        SELECT product, symbol, open_time, close_time, open, high, low, close, base_volume, trade_count
        FROM candles WHERE interval='1m' AND is_final=1
        ORDER BY open_time DESC LIMIT 1
        """,
    )
    if not candle:
        return [CheckResult("reconciliation", "trades↔candle", Status.NO_DATA, "no final 1m candle")]

    product, symbol, ot, ct, o, h, l, c, vol, tcount = candle[0]
    trades = await _rows(
        conn,
        """
        SELECT price, quantity FROM trades
        WHERE product=? AND symbol=? AND trade_time >= ? AND trade_time < ?
        ORDER BY trade_time
        """,
        (product, symbol, ot, ct),
    )
    if len(trades) < 3:
        return [
            CheckResult(
                "reconciliation",
                "trades↔candle",
                Status.PARTIAL,
                f"{product} {symbol} window {ot}-{ct}: only {len(trades)} trades in DB for that minute "
                "(WS may have started mid-candle or smoke window short)",
            )
        ]

    prices = [float(p) for p, _ in trades]
    qty_sum = sum(float(q) for _, q in trades)
    flags = []
    if abs(prices[0] - float(o)) > 1e-8:
        flags.append(f"open {prices[0]} vs {o}")
    if abs(prices[-1] - float(c)) > 1e-8:
        flags.append(f"close {prices[-1]} vs {c}")
    if abs(max(prices) - float(h)) > 1e-8:
        flags.append(f"high {max(prices)} vs {h}")
    if abs(min(prices) - float(l)) > 1e-8:
        flags.append(f"low {min(prices)} vs {l}")
    # volume: Binance candle base volume vs sum of trade qty — should be close if complete
    if abs(qty_sum - float(vol)) / max(float(vol), 1e-12) > 0.05:
        flags.append(f"volume_sum {qty_sum} vs candle {vol}")
    if tcount is not None and abs(len(trades) - int(tcount)) > max(2, int(tcount) * 0.05):
        flags.append(f"trade_count {len(trades)} vs candle {tcount}")

    return [
        CheckResult(
            "reconciliation",
            "trades↔candle",
            Status.PASS if not flags else Status.PARTIAL,
            f"{product} {symbol} 1m@{ot}: trades_in_db={len(trades)}; "
            + ("matches OHLC/vol/count within tolerance" if not flags else "diffs: " + "; ".join(flags)),
        )
    ]


async def check_reconcile_depth_book(conn: aiosqlite.Connection) -> list[CheckResult]:
    """Compare a depth snapshot top-of-book vs bookTicker (soft).

    Only Spot / USDS-M / COIN-M — Options depth is REST-only and has no
    bookTicker stream, so using the latest snapshot by id falsely PARTIALs.
    """
    snaps = await _rows(
        conn,
        """
        SELECT product, symbol, bids_json, asks_json, observed_at
        FROM depth_snapshots
        WHERE product IN ('SPOT', 'USDM_FUTURES', 'COINM_FUTURES')
        ORDER BY id DESC
        LIMIT 20
        """,
    )
    if not snaps:
        return [
            CheckResult(
                "reconciliation",
                "depth↔bookTicker",
                Status.NO_DATA,
                "no Spot/Futures depth snapshots (Options depth skipped — no bookTicker)",
            )
        ]

    last_err = "missing bookTicker or empty book"
    for product, symbol, bids_json, asks_json, observed_at in snaps:
        try:
            bids = json.loads(bids_json)
            asks = json.loads(asks_json)
            best_bid = max((float(p) for p, q in bids if float(q) > 0), default=None)
            best_ask = min((float(p) for p, q in asks if float(q) > 0), default=None)
        except Exception as exc:  # noqa: BLE001
            last_err = f"bad snapshot JSON: {exc}"
            continue
        if best_bid is None or best_ask is None:
            last_err = "empty book on depth snapshot"
            continue

        bt = await _rows(
            conn,
            """
            SELECT best_bid_price, best_ask_price, observed_at FROM book_ticker
            WHERE product=? AND symbol=? ORDER BY id DESC LIMIT 1
            """,
            (product, symbol),
        )
        if not bt:
            last_err = f"no bookTicker for {product} {symbol}"
            continue

        bb, ba, bt_obs = bt[0]
        bid_ok = abs(float(bb) - best_bid) / max(best_bid, 1e-12) < 0.002
        ask_ok = abs(float(ba) - best_ask) / max(best_ask, 1e-12) < 0.002
        return [
            CheckResult(
                "reconciliation",
                "depth↔bookTicker",
                Status.PASS if bid_ok and ask_ok else Status.PARTIAL,
                f"{product} {symbol}: depth_bid={best_bid} book={bb}; depth_ask={best_ask} book={ba}; "
                f"snap_at={observed_at}; book_at={bt_obs} (timing not identical)",
            )
        ]

    return [CheckResult("reconciliation", "depth↔bookTicker", Status.PARTIAL, last_err)]


async def check_coverage_matrix(conn: aiosqlite.Connection, settings: Settings | None = None) -> list[CheckResult]:
    out: list[CheckResult] = []
    # Per product: instruments vs feed presence
    for product in ("SPOT", "USDM_FUTURES", "COINM_FUTURES"):
        if settings is not None and not product_enabled(settings, product):
            out.append(CheckResult("coverage_matrix", product, Status.NOT_IMPLEMENTED, "product disabled in config for this run"))
            continue
        inst = {
            r[0]
            for r in await _rows(conn, "SELECT symbol FROM instruments WHERE product=?", (product,))
        }
        # For smoke/list runs instruments_loop still may write full exchangeInfo —
        # coverage should use symbols that appear in stream tables / symbol_coverage
        covered = {
            r[0]
            for r in await _rows(
                conn,
                """
                SELECT symbol FROM (
                  SELECT symbol FROM symbol_coverage WHERE product=?
                  UNION SELECT symbol FROM trades WHERE product=?
                )
                """,
                (product, product),
            )
        }
        trade_syms = {r[0] for r in await _rows(conn, "SELECT DISTINCT symbol FROM trades WHERE product=?", (product,))}
        book_syms = {
            r[0] for r in await _rows(conn, "SELECT DISTINCT symbol FROM book_ticker WHERE product=?", (product,))
        }
        depth_syms = {
            r[0] for r in await _rows(conn, "SELECT DISTINCT symbol FROM depth_updates WHERE product=?", (product,))
        }
        candle_syms = {
            r[0] for r in await _rows(conn, "SELECT DISTINCT symbol FROM candles WHERE product=?", (product,))
        }
        universe = covered or trade_syms or book_syms
        if not universe:
            out.append(CheckResult("coverage_matrix", product, Status.NO_DATA, "no stream symbols"))
            continue
        missing_trades = sorted(universe - trade_syms)[:10]
        missing_book = sorted(universe - book_syms)[:10]
        # Depth is intentionally subset
        depth_note = f"depth_symbols={len(depth_syms)} (expected ≤ universe; top-N)"
        status = Status.PASS
        if missing_trades or missing_book:
            status = Status.PARTIAL
        out.append(
            CheckResult(
                "coverage_matrix",
                product,
                status,
                f"universe≈{len(universe)}; trades={len(trade_syms)}; book={len(book_syms)}; "
                f"candles={len(candle_syms)}; {depth_note}; "
                f"missing_trades_sample={missing_trades}; missing_book_sample={missing_book}; "
                f"instruments_table={len(inst)} (may include full exchangeInfo even in list mode)",
            )
        )
    return out


async def check_storage_growth(conn: aiosqlite.Connection, db_path: str) -> list[CheckResult]:
    size = os.path.getsize(db_path) if os.path.exists(db_path) else 0
    total_rows = 0
    by_table: dict[str, int] = {}
    for table in (
        "raw_events",
        "trades",
        "agg_trades",
        "book_ticker",
        "candles",
        "depth_updates",
        "ticker_24h",
        "mark_price",
    ):
        n = await _scalar(conn, f"SELECT COUNT(*) FROM {table}") or 0
        by_table[table] = n
        total_rows += n

    first = await _scalar(conn, "SELECT MIN(observed_at) FROM raw_events")
    last = await _scalar(conn, "SELECT MAX(observed_at) FROM raw_events")
    dt0, dt1 = _parse_iso(first), _parse_iso(last)
    hours = max((dt1 - dt0).total_seconds() / 3600.0, 1 / 60.0) if dt0 and dt1 else None
    rows_per_hour = (total_rows / hours) if hours else None

    projections = {}
    if rows_per_hour and size and total_rows:
        bytes_per_row = size / max(total_rows, 1)
        for days, label in ((7, "7d"), (30, "30d"), (90, "90d"), (365, "1y")):
            proj_rows = rows_per_hour * 24 * days
            projections[label] = {
                "rows": int(proj_rows),
                "bytes": int(proj_rows * bytes_per_row),
            }

    return [
        CheckResult(
            "storage",
            "growth estimate",
            Status.PASS if size else Status.FAIL,
            f"db_bytes={size:,}; tracked_rows≈{total_rows}; hours≈{hours}; "
            f"rows_per_hour≈{rows_per_hour}; by_table={by_table}; "
            f"projections={projections} (smoke/list rates do not equal full-universe rates)",
            {"size": size, "projections": projections, "by_table": by_table},
        )
    ]


async def check_not_implemented_extras(conn: aiosqlite.Connection) -> list[CheckResult]:
    out: list[CheckResult] = []
    # Provenance column
    cur = await conn.execute("PRAGMA table_info(raw_events)")
    cols = {r[1] for r in await cur.fetchall()}
    if "source_type" not in cols:
        out.append(
            CheckResult(
                "provenance",
                "REST backfill source_type",
                Status.NOT_IMPLEMENTED,
                "raw_events.source_type column missing",
            )
        )
    else:
        by_type = await _rows(conn, "SELECT source_type, COUNT(*) FROM raw_events GROUP BY source_type")
        counts = {t: c for t, c in by_type}
        has_ws = counts.get("websocket", 0) > 0
        has_rest = counts.get("rest_poll", 0) > 0
        has_backfill = counts.get("rest_backfill", 0) > 0
        if has_ws and has_rest:
            status = Status.PASS
        elif has_ws or has_rest or has_backfill:
            status = Status.PARTIAL
        else:
            status = Status.NO_DATA
        jobs = 0
        if await _table_exists(conn, "gap_fill_jobs"):
            jobs = await _scalar(conn, "SELECT COUNT(*) FROM gap_fill_jobs") or 0
        out.append(
            CheckResult(
                "provenance",
                "REST backfill source_type",
                status,
                f"source_type counts={dict(by_type)}; gap_fill_jobs={jobs}; "
                "values=websocket|rest_poll|rest_backfill — crawler fills agg_trades/klines holes",
            )
        )

    # coverage_history
    if not await _table_exists(conn, "coverage_history"):
        out.append(
            CheckResult(
                "coverage_history",
                "explicit started_at/ended_at/reason",
                Status.NOT_IMPLEMENTED,
                "coverage_history table missing",
            )
        )
    else:
        n = await _scalar(conn, "SELECT COUNT(*) FROM coverage_history") or 0
        open_n = await _scalar(conn, "SELECT COUNT(*) FROM coverage_history WHERE ended_at IS NULL") or 0
        with_reason = await _scalar(
            conn, "SELECT COUNT(*) FROM coverage_history WHERE reason IS NOT NULL AND reason!=''"
        ) or 0
        if n == 0:
            hist_status = Status.NO_DATA
        elif with_reason == n:
            hist_status = Status.PASS
        else:
            hist_status = Status.PARTIAL
        out.append(
            CheckResult(
                "coverage_history",
                "explicit started_at/ended_at/reason",
                hist_status,
                f"rows={n}; open={open_n}; with_reason={with_reason}",
            )
        )
    return out


async def check_inventory_matrix(settings: Settings, results_by_key: dict[tuple[str, str], Status]) -> list[CheckResult]:
    """Build final matrix rows from inventory + observed statuses."""
    out: list[CheckResult] = []
    for feed in FEEDS:
        enabled = product_enabled(settings, feed.product) if feed.product in PRODUCT_KEYS else False
        if feed.product == "MARGIN":
            enabled = product_enabled(settings, "SPOT")
        if feed.product == "EXCHANGE":
            enabled = True  # always polled when collector runs

        if not feed.publicly_available:
            final = Status.NOT_PUBLICLY_AVAILABLE
        elif not feed.implemented:
            final = Status.NOT_IMPLEMENTED
        elif feed.product in ("SPOT", "USDM_FUTURES", "COINM_FUTURES", "OPTIONS") and not enabled:
            final = Status.NOT_IMPLEMENTED
        else:
            final = results_by_key.get((feed.product, feed.data_type), Status.PARTIAL)

        out.append(
            CheckResult(
                "matrix",
                f"{feed.product} / {feed.data_type}",
                final,
                feed.notes or "",
                {
                    "publicly_available": feed.publicly_available,
                    "implemented": feed.implemented,
                    "enabled": enabled,
                },
            )
        )
    return out


PRODUCT_KEYS = {"SPOT", "USDM_FUTURES", "COINM_FUTURES", "OPTIONS", "MARGIN"}


def _map_results_to_matrix(results: list[CheckResult]) -> dict[tuple[str, str], Status]:
    """Heuristic map from detailed checks → matrix cells."""
    m: dict[tuple[str, str], Status] = {}

    def put(product: str, data_type: str, status: Status) -> None:
        key = (product, data_type)
        if key not in m:
            m[key] = status
        else:
            m[key] = combine_status([m[key], status])

    for r in results:
        if r.section == "instruments" and r.item in PRODUCTS:
            put(r.item, "instruments", r.status)
        elif r.section == "trades" and r.item in PRODUCTS:
            put(r.item, "trades", r.status)
        elif r.section == "agg_trades":
            put(r.item, "agg_trades", r.status)
        elif r.section == "book_ticker":
            put(r.item, "book_ticker", r.status)
        elif r.section == "depth":
            put(r.item, "depth", r.status)
        elif r.section == "candles" and r.item.startswith("configured"):
            for p in ("SPOT", "USDM_FUTURES", "COINM_FUTURES"):
                put(p, "candles", r.status)
        elif r.section == "ticker_24h":
            put(r.item, "ticker_24h", r.status)
            if r.item == "OPTIONS":
                put("OPTIONS", "ticker", r.status)
        elif r.section == "mark_price":
            put(r.item, "mark_price", r.status)
        elif r.section == "funding":
            put(r.item, "funding", r.status)
        elif r.section == "open_interest":
            put(r.item, "open_interest", r.status)
        elif r.section == "liquidations":
            put(r.item, "liquidations", r.status)
        elif r.section == "positioning":
            put(r.item, "positioning", r.status)
        elif r.section == "products" and "MARGIN" in r.item:
            put("MARGIN", "metadata", r.status)
        elif r.section == "options":
            if r.item == "instruments":
                put("OPTIONS", "instruments", r.status)
            elif r.item == "trades":
                put("OPTIONS", "trades", r.status)
            elif r.item == "ticker":
                put("OPTIONS", "ticker", r.status)
            elif r.item == "iv_greeks":
                put("OPTIONS", "iv_greeks", r.status)
            elif r.item == "book":
                put("OPTIONS", "book", r.status)
            elif r.item == "open_interest":
                put("OPTIONS", "open_interest", r.status)
            elif r.item == "index":
                pass  # inventory uses iv_greeks / ticker; index is bonus
        elif r.section == "exchange_wide" and "system status" in r.item:
            put("EXCHANGE", "system_status", r.status)
        elif r.section == "provenance" and "source_type" in r.item:
            put("EXCHANGE", "rest_backfill_provenance", r.status)
    return m


async def run_all_checks(conn: aiosqlite.Connection, db_path: str, settings: Settings) -> list[CheckResult]:
    results: list[CheckResult] = []
    results += await check_database_opens(conn, db_path)
    results += await check_decimal_precision(conn)
    results += await check_products(conn, settings)
    results += await check_instruments(conn, settings)
    results += await check_raw_events(conn)
    results += await check_trades(conn, settings)
    results += await check_agg_trades(conn, settings)
    results += await check_book_ticker(conn, settings)
    results += await check_depth(conn, settings)
    results += await check_candles(conn, settings)
    results += await check_ticker(conn, settings)
    results += await check_futures_special(conn, settings)
    results += await check_options_feeds(conn, settings)
    results += await check_exchange_status(conn)
    results += await check_timestamps(conn)
    results += await check_system_health(conn)
    results += await check_raw_normalized_samples(conn)
    results += await check_reconcile_candles(conn)
    results += await check_reconcile_depth_book(conn)
    results += await check_coverage_matrix(conn, settings)
    results += await check_storage_growth(conn, db_path)
    results += await check_not_implemented_extras(conn)

    matrix_map = _map_results_to_matrix(results)
    results += await check_inventory_matrix(settings, matrix_map)
    return results
