"""End of video 2.4 — example using the WebSocket connector class.

The async function from v2.3 has been extracted to the library at
src/quantlake/bronze/connectors/binance_spot_websocket.py. This example
collapses to 8 lines: instantiate the connector, await each closed bar,
print.

Same shape as examples/bronze/binance_spot_ohlcv.py at v1.4 — both
demonstrate "the library does the work, the example just consumes it".
"""
import asyncio

from quantlake.bronze.connectors.binance_spot_websocket import BinanceSpotOHLCVWebsocketConnector


async def main():
    ws = BinanceSpotOHLCVWebsocketConnector(timeframe="1m")
    async for bar in ws.stream(["BTCUSDT", "ETHUSDT"]):
        print(bar)

asyncio.run(main())