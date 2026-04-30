"""End of video 2.4 — Binance spot WebSocket connector class.

Same body as the stream_klines() function from v2.3, now wrapped in a
class that respects the StreamConnector contract.

TABLE_NAME matches the REST and bulk connectors — all three Binance
spot connectors write to the same Delta table on disk.
"""
import asyncio
import json
from datetime import datetime, timezone
from typing import AsyncIterator

import websockets

from quantlake.bronze.base import StreamConnector


class BinanceSpotOHLCVWebsocketConnector(StreamConnector):
    """Streams spot OHLCV from Binance combined WebSocket (one connection for all symbols).

    Reconnects automatically on drop.

    Yields one dict per closed candle. Keys: timestamp, timestamp_close,
    ingested_at, symbol, open, high, low, close, volume.
    """

    TABLE_NAME = "binance_spot_ohlcv"
    _WS_BASE = "wss://stream.binance.com:9443/stream?streams="
    _RECONNECT_DELAY = 5  # seconds before reconnect attempt

    def __init__(self, timeframe: str = "1m"):
        self.timeframe = timeframe

    async def stream(self, symbols: list[str]) -> AsyncIterator[dict]:
        streams = "/".join(f"{s.lower()}@kline_{self.timeframe}" for s in symbols)
        url = self._WS_BASE + streams

        while True:
            try:
                async with websockets.connect(url) as ws:
                    async for raw in ws:
                        ingested_at = datetime.now(timezone.utc)
                        msg = json.loads(raw)
                        k = msg["data"]["k"]

                        if not k["x"]:  # candle not closed yet
                            continue

                        yield {
                            "timestamp":       datetime.fromtimestamp(k["t"] / 1000, tz=timezone.utc),
                            "timestamp_close": datetime.fromtimestamp(k["T"] / 1000, tz=timezone.utc),
                            "ingested_at":     ingested_at,
                            "symbol":          k["s"],
                            "open":            float(k["o"]),
                            "high":            float(k["h"]),
                            "low":             float(k["l"]),
                            "close":           float(k["c"]),
                            "volume":          float(k["v"]),
                        }
            except (websockets.ConnectionClosed, OSError):
                await asyncio.sleep(self._RECONNECT_DELAY)
