"""End of v0.7.5 - Live ML signal + WebSocket broadcast, Binance BTCUSDT.

Identical to ml_based_strategy.py (v0.7.4) with one new thing: every
gold bar written is also broadcast on a local WebSocket so a separate
consumer process (consumer.py) can react to it - print, place an order,
log, whatever - without coupling to the strategy code.

Usage:
    poetry run python applications/live/ml_based_strategy/ml_based_strategy_ws.py
"""
import asyncio
import json
import pickle
import sys
from collections import deque
from pathlib import Path

import polars as pl
import websockets

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import quantlake.gold.ingest as gold
from quantlake.bronze.connectors.binance_spot_rest import BinanceSpotOHLCVRestConnector
from quantlake.bronze.connectors.binance_spot_websocket import BinanceSpotOHLCVWebsocketConnector
from quantlake.live import run

GOLD_TABLE       = "ml_based_strategy"
TIMEFRAME        = "5m"
SYMBOL           = "BTCUSDT"
SILVER_TABLE     = BinanceSpotOHLCVWebsocketConnector.TABLE_NAME
N_FEATURES       = 5
MODEL_PATH       = Path(__file__).parent / "model.pkl"
WS_HOST, WS_PORT = "localhost", 8765

ws   = BinanceSpotOHLCVWebsocketConnector(timeframe="1m")
rest = BinanceSpotOHLCVRestConnector(timeframe="1m")


class MLPredictor:
    """Stateful predictor - keeps the last N+1 closes, returns predict_proba."""

    def __init__(self, model_path: Path, n: int):
        if not model_path.exists():
            raise FileNotFoundError(
                f"{model_path} not found - run train.ipynb in this folder first."
            )
        with open(model_path, "rb") as f:
            self.model = pickle.load(f)
        self.n = n
        self.history: deque[float] = deque(maxlen=n + 1)

    def predict(self, close: float) -> float | None:
        self.history.append(close)
        if len(self.history) < self.n + 1:
            return None
        prices = list(self.history)
        returns = [(prices[i + 1] - prices[i]) / prices[i] for i in range(self.n)]
        return float(self.model.predict_proba([returns])[0][1])


predictor = MLPredictor(MODEL_PATH, N_FEATURES)
clients: set = set()
loop_ref: asyncio.AbstractEventLoop | None = None


def _broadcast_sync(payload: dict) -> None:
    """Schedule a broadcast onto the running event loop from sync code."""
    if loop_ref is None or not clients:
        return
    msg = json.dumps(payload, default=str)
    for ws_client in list(clients):
        asyncio.run_coroutine_threadsafe(ws_client.send(msg), loop_ref)


def transform_gold(gold_bar: pl.DataFrame, symbol: str) -> pl.DataFrame:
    """Predict, append ml_signal, broadcast the latest live bar on the WS."""
    if gold_bar.is_empty():
        return gold_bar
    signals = [predictor.predict(float(c)) for c in gold_bar["close"].to_list()]
    out = gold_bar.with_columns(pl.Series("ml_signal", signals, dtype=pl.Float64))

    # Broadcast only the latest bar (the live one). During rebuild this
    # function is called once with the whole history - we don't broadcast
    # those, only what happens after the loop is running.
    if loop_ref is not None and len(out) == 1:
        row = out.row(0, named=True)
        _broadcast_sync({
            "symbol":     symbol,
            "timestamp":  row["timestamp"].isoformat(),
            "close":      row["close"],
            "ml_signal":  row["ml_signal"],
        })
    return out


async def _ws_handler(websocket):
    clients.add(websocket)
    try:
        await websocket.wait_closed()
    finally:
        clients.discard(websocket)


async def main() -> None:
    global loop_ref
    loop_ref = asyncio.get_running_loop()
    async with websockets.serve(_ws_handler, WS_HOST, WS_PORT):
        print(f"WS server: ws://{WS_HOST}:{WS_PORT}")
        await run(
            ws_connector=ws,
            rest_connector=rest,
            symbols=[SYMBOL],
            gold_table=GOLD_TABLE,
            timeframe=TIMEFRAME,
            transform_gold=transform_gold,
        )


print(f"Rebuilding gold/{GOLD_TABLE}/{TIMEFRAME} from silver...")
built = gold.rebuild_from_silver(
    silver_table=SILVER_TABLE,
    symbol=SYMBOL,
    gold_table=GOLD_TABLE,
    timeframe=TIMEFRAME,
    transform_gold=transform_gold,
)
rows = 0 if built is None else len(built)
print(f"  {SYMBOL}: {rows:,} bars")

asyncio.run(main())






