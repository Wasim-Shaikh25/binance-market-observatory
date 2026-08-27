"""Live probe: which USDS-M combined-stream names actually deliver messages."""
import asyncio
import json
from collections import Counter

import aiohttp

STREAMS = [
    "btcusdt@trade",
    "btcusdt@aggTrade",
    "btcusdt@bookTicker",
    "btcusdt@ticker",
    "btcusdt@kline_1m",
    "btcusdt@markPrice@1s",
    "!forceOrder@arr",
]
URL = "wss://fstream.binance.com/stream?streams=" + "/".join(STREAMS)


async def main() -> None:
    counts: Counter[str] = Counter()
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(URL, heartbeat=20) as ws:
            print("connected", URL[:80], "...")
            deadline = asyncio.get_event_loop().time() + 15
            async for msg in ws:
                if asyncio.get_event_loop().time() > deadline:
                    break
                if msg.type != aiohttp.WSMsgType.TEXT:
                    continue
                data = json.loads(msg.data)
                counts[data.get("stream", "?")] += 1
    print("counts after 15s:")
    for k, v in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {k}: {v}")
    missing = [s for s in STREAMS if counts.get(s, 0) == 0]
    print("missing:", missing)


if __name__ == "__main__":
    asyncio.run(main())
