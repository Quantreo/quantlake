"""End of v0.7.5 - Subscribe to ml_based_strategy_ws.py's WebSocket
and print each gold bar.

In a real setup, this is where you'd place an order on a broker
(Binance, Capital.com, MT5, ...) based on ``ml_signal``. Here we just
print, so the data -> decision -> execution flow is visible without any
broker risk.

Run ml_based_strategy_ws.py first in another terminal, then:
    poetry run python applications/live/ml_based_strategy/consumer.py
"""
import asyncio
import json

import websockets

WS_URL = "ws://localhost:8765"


async def main() -> None:
    async with websockets.connect(WS_URL) as ws:
        print(f"Connected to {WS_URL}\n")
        async for raw in ws:
            bar = json.loads(raw)
            sig = bar["ml_signal"]
            sig_str = f"{sig:.3f}" if sig is not None else "  -  "
            print(
                f"[{bar['timestamp']}] {bar['symbol']:10s}"
                f"  close={bar['close']:.2f}  ml_signal={sig_str}"
            )


asyncio.run(main())
