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
