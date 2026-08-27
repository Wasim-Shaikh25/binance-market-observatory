"""Raw archive + dual-write config tests."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import zstandard as zstd

from src.config import load_settings
from src.models import Envelope
from src.raw_archive import RawArchiveWriter
from src.storage import DBWriter, open_db


def test_settings_loads_sinks_defaults(tmp_path):
    p = tmp_path / "s.yaml"
    p.write_text(
        """
database:
  path: data/x.db
products:
  spot:
    enabled: false
    rest_base_url: https://api.binance.com
    ws_base_url: wss://stream.binance.com:9443
rate_limits: {}
""",
        encoding="utf-8",
    )
    s = load_settings(str(p))
    assert s.clickhouse.enabled is False
    assert s.raw_archive.enabled is False
    assert s.database_persist is True


def test_settings_persist_false(tmp_path):
    p = tmp_path / "s.yaml"
    p.write_text(
        """
database:
  path: data/x.db
  persist: false
products:
  spot:
    enabled: false
    rest_base_url: https://api.binance.com
    ws_base_url: wss://stream.binance.com:9443
rate_limits: {}
""",
        encoding="utf-8",
    )
    assert load_settings(str(p)).database_persist is False


def test_clickhouse_norm_covers_core_kinds():
    from src.clickhouse_sink import ClickHouseSink
    from src.config import ClickHouseSinkConfig

    sink = ClickHouseSink(ClickHouseSinkConfig(), database="bmo_test")
    trade = Envelope(
        product="SPOT",
        stream_name="btcusdt@trade",
        source_endpoint="wss://x",
        kind="trade",
        payload={"trade_id": 1, "price": "1", "quantity": "1", "trade_time": 1, "buyer_maker": False},
        symbol="BTCUSDT",
    )
    table, line = sink._norm_line(trade)
    assert table == "trades"
    assert "BTCUSDT" in line

    candle = Envelope(
        product="SPOT",
        stream_name="btcusdt@kline_1m",
        source_endpoint="wss://x",
        kind="candle",
        payload={
            "interval": "1m",
            "open_time": 1,
            "close_time": 2,
            "open": "1",
            "high": "1",
            "low": "1",
            "close": "1",
            "base_volume": "1",
            "quote_volume": "1",
            "is_final": True,
        },
        symbol="BTCUSDT",
    )
    table, line = sink._norm_line(candle)
    assert table == "candles"

    oi = Envelope(
        product="USDM_FUTURES",
        stream_name="rest",
        source_endpoint="/fapi/v1/openInterest",
        kind="open_interest",
        payload={"open_interest": "10", "observation_time": 1},
        symbol="BTCUSDT",
    )
    table, _ = sink._norm_line(oi)
    assert table == "open_interest"

    mark = Envelope(
        product="OPTIONS",
        stream_name="rest",
        source_endpoint="/eapi/v1/mark",
        kind="options_mark",
        payload={"mark_price": "1", "mark_iv": "0.5", "raw": {}},
        symbol="BTC-260828-65000-C",
    )
    table, _ = sink._norm_line(mark)
    assert table == "options_mark"

    lines = sink._instrument_lines(
        Envelope(
            product="SPOT",
            stream_name="rest",
            source_endpoint="/api/v3/exchangeInfo",
            kind="instrument_snapshot",
            payload={"status": "TRADING", "base_asset": "BTC", "quote_asset": "USDT", "tick_size": "0.01", "step_size": "0.001"},
            symbol="BTCUSDT",
        )
    )
    assert {t for t, _ in lines} == {"instruments", "instrument_snapshots"}


def test_raw_archive_roundtrip(tmp_path):
    path = str(tmp_path / "raw.ndjson.zst")
    w = RawArchiveWriter(path, rotate="none")
    env = Envelope(
        product="SPOT",
        stream_name="btcusdt@trade",
        source_endpoint="wss://stream.binance.com:9443",
        kind="trade",
        payload={"trade_id": 1, "price": "1.0", "quantity": "2.0", "trade_time": 1, "buyer_maker": False},
        symbol="BTCUSDT",
    )
    w.append(env)
    w.append(env)
    w.close()
    dctx = zstd.ZstdDecompressor()
    with open(path, "rb") as f, dctx.stream_reader(f) as reader:
        text = reader.read().decode("utf-8")
    lines = [json.loads(x) for x in text.strip().splitlines()]
    assert len(lines) == 2
    assert lines[0]["product"] == "SPOT"
    assert lines[0]["payload"]["price"] == "1.0"
    assert lines[0]["source_type"] == "websocket"


async def test_dbwriter_also_writes_archive(tmp_path):
    db = str(tmp_path / "t.db")
    arch = str(tmp_path / "a.ndjson.zst")
    conn = await open_db(db)
    queue: asyncio.Queue = asyncio.Queue()
    archive = RawArchiveWriter(arch, rotate="none")
    writer = DBWriter(conn, queue, raw_archive=archive, clickhouse=None)
    task = asyncio.create_task(writer.run())
    env = Envelope(
        product="SPOT",
        stream_name="btcusdt@trade",
        source_endpoint="wss://x",
        kind="trade",
        payload={"trade_id": 7, "price": "1", "quantity": "1", "trade_time": 1, "buyer_maker": False},
        symbol="BTCUSDT",
    )
    await queue.put(env)
    await queue.put(None)
    await task
    await conn.close()
    dctx = zstd.ZstdDecompressor()
    with open(arch, "rb") as f, dctx.stream_reader(f) as reader:
        text = reader.read().decode("utf-8")
    assert '"trade_id":7' in text
    assert Path(db).exists()
