"""End of video 2.3 — WebSocket primer (with async/await commentary).

This file is the FIRST place asyncio shows up in the course. Read the
comments — every async keyword has a "why" attached.

The big idea: a WebSocket connection spends 99% of its time WAITING for
the next message from the network. If we used regular blocking I/O, the
whole Python process would freeze during each wait. asyncio lets the
program "park" the wait and resume when the message arrives, without
blocking the rest of the program. For one WebSocket it doesn't matter
much. But the same code scales to many connections, ping/pong tasks,
and disk writes happening in parallel — that's why we start with async
even on a simple example.

"""
# asyncio is the standard library for cooperative concurrency in Python.
# It manages an "event loop" that can run many async tasks taking turns
# whenever one of them is waiting on I/O.

import asyncio
import json
from datetime import datetime, timezone

from typing import AsyncIterator
import websockets


_RECONNECT_DELAY = 5

async def stream_klines(symbols: list[str], timeframe: str = "1m") -> AsyncIterator[dict]:
    """Stream closed klines for multiple symbols over a single WebSocket connection.

    Yields one dict per closed candle. Auto-reconnects on drop.
    """

    # Pure synchronous string-building. Nothing async here. Stream ex = btcusdt@kline_1m/ethusdt@kline_1m
    streams = "/".join(f"{s.lower()}@kline_{timeframe}" for s in symbols)
    url = f"wss://stream.binance.com:9443/stream?streams={streams}"

    while True:
        try:
            async with websockets.connect(url) as ws:
                async for raw in ws:
                    # The moment we received this message, useful for live. latency metrics in Module 4.
                    ingested_at = datetime.now(timezone.utc)

                    msg = json.loads(raw)
                    k = msg["data"]["k"]

                    # Binance pushes the same bar MANY times while it's forming
                    # (every few hundred ms, with updated H/L/C). We only want
                    # CLOSED bars. The `x` flag tells us if it's the final
                    # version of this bar.
                    if not k["x"]:
                        continue

                    # ─── Why `yield` inside an async function ────────────────
                    # `yield` here makes this whole function an async
                    # generator. Each `yield` pauses execution and hands a
                    # value to the caller (which awaits it via `async for`).
                    # When the caller asks for the next value, execution
                    # resumes from after this `yield` — including the `async
                    # for raw in ws` loop that resumes waiting on the next
                    # message.
                    yield {
                        "timestamp": datetime.fromtimestamp(k["t"] / 1000, tz=timezone.utc),
                        "timestamp_close": datetime.fromtimestamp(k["T"] / 1000, tz=timezone.utc),
                        "ingested_at": ingested_at,
                        "symbol": k["s"],
                        "open": float(k["o"]),
                        "high": float(k["h"]),
                        "low": float(k["l"]),
                        "close": float(k["c"]),
                        "volume": float(k["v"]),
                    }
        except (websockets.ConnectionClosed, OSError):
            # ─── Why `await asyncio.sleep` (NOT `time.sleep`) ────────────────
            # `time.sleep(5)` would freeze the whole Python process for 5
            # seconds. The event loop can't do anything else during that
            # time — bad behavior in a script that may have other async
            # tasks running concurrently.
            #
            # `asyncio.sleep(5)` parks the wait. The event loop is free to
            # run other tasks for those 5 seconds. As a habit: in async
            # code, NEVER use `time.sleep`. Always `asyncio.sleep`.
            await asyncio.sleep(_RECONNECT_DELAY)


async def run_fetch():
    async for bar in stream_klines(["BTCUSDT", "ETHUSDT"]):
        print(bar)

asyncio.run(run_fetch())