"""Probe USDM stream groups separately to find what fstream actually accepts."""
import asyncio
import json
from collections import Counter

import aiohttp

GROUPS = {
    "mark_only": ["btcusdt@markPrice@1s"],
    "agg_only": ["btcusdt@aggTrade"],
    "ticker_only": ["btcusdt@ticker"],
    "kline_only": ["btcusdt@kline_1m"],
    "force_only": ["!forceOrder@arr"],
    "mark_encoded": None,  # special
}


async def probe(name: str, streams: list[str], seconds: float = 8) -> None:
    url = "wss://fstream.binance.com/stream?streams=" + "/".join(streams)
    counts: Counter[str] = Counter()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(url, heartbeat=20) as ws:
                deadline = asyncio.get_event_loop().time() + seconds
                async for msg in ws:
                    if asyncio.get_event_loop().time() > deadline:
                        break
                    if msg.type != aiohttp.WSMsgType.TEXT:
                        continue
                    data = json.loads(msg.data)
                    counts[data.get("stream", data.get("e", "?"))] += 1
    except Exception as exc:  # noqa: BLE001
        print(f"{name}: ERROR {exc}")
        return
    print(f"{name}: {dict(counts)} url_len={len(url)}")


async def probe_encoded() -> None:
    from urllib.parse import quote
    streams = ["btcusdt@markPrice@1s", "btcusdt@aggTrade", "btcusdt@ticker"]
    joined = "/".join(streams)
    url = "wss://fstream.binance.com/stream?streams=" + quote(joined, safe="")
    counts: Counter[str] = Counter()
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(url, heartbeat=20) as ws:
            deadline = asyncio.get_event_loop().time() + 8
            async for msg in ws:
                if asyncio.get_event_loop().time() > deadline:
                    break
                if msg.type != aiohttp.WSMsgType.TEXT:
                    continue
                data = json.loads(msg.data)
                counts[data.get("stream", "?")] += 1
    print(f"encoded_group: {dict(counts)}")


async def main() -> None:
    for name, streams in GROUPS.items():
        if streams is None:
            continue
        await probe(name, streams)
    await probe_encoded()
    # trade+book with mark — does adding trade/book kill mark?
    await probe("trade_book_mark", ["btcusdt@trade", "btcusdt@bookTicker", "btcusdt@markPrice@1s"])
    await probe("all_without_book", ["btcusdt@trade", "btcusdt@aggTrade", "btcusdt@ticker", "btcusdt@kline_1m", "btcusdt@markPrice@1s", "!forceOrder@arr"])


if __name__ == "__main__":
    asyncio.run(main())
