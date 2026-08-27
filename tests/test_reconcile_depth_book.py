"""depth↔bookTicker reconcile must ignore Options snapshots (no bookTicker)."""

from __future__ import annotations

import json

import pytest

from src.storage import open_db
from src.validation.checks import check_reconcile_depth_book
from src.validation.status import Status


@pytest.mark.asyncio
async def test_reconcile_skips_options_depth_uses_spot(tmp_path):
    db = str(tmp_path / "t.db")
    conn = await open_db(db)
    # Spot depth + matching bookTicker
    await conn.execute(
        """
        INSERT INTO depth_snapshots
        (exchange, product, symbol, last_update_id, bids_json, asks_json, observed_at)
        VALUES ('binance','SPOT','BTCUSDT',1,?,?,?)
        """,
        (
            json.dumps([["100.0", "1"]]),
            json.dumps([["100.1", "1"]]),
            "2026-08-27T00:00:00+00:00",
        ),
    )
    await conn.execute(
        """
        INSERT INTO book_ticker
        (exchange, product, symbol, best_bid_price, best_bid_qty, best_ask_price, best_ask_qty, observed_at)
        VALUES ('binance','SPOT','BTCUSDT','100.0','1','100.1','1',?)
        """,
        ("2026-08-27T00:00:01+00:00",),
    )
    # Later Options depth (would falsely PARTIAL under old "ORDER BY id DESC LIMIT 1")
    await conn.execute(
        """
        INSERT INTO depth_snapshots
        (exchange, product, symbol, last_update_id, bids_json, asks_json, observed_at)
        VALUES ('binance','OPTIONS','BTC-OPT',2,?,?,?)
        """,
        (
            json.dumps([["50.0", "1"]]),
            json.dumps([["51.0", "1"]]),
            "2026-08-27T00:01:00+00:00",
        ),
    )
    await conn.commit()
    results = await check_reconcile_depth_book(conn)
    await conn.close()
    assert len(results) == 1
    assert results[0].status == Status.PASS
    assert "SPOT" in results[0].evidence
    assert "BTCUSDT" in results[0].evidence
