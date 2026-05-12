"""End of v0.7.4 - Live ML signal, Binance BTCUSDT.

Same skeleton as the other M7 strategies. The new thing: a small
``transform_gold`` callback that adds an ``ml_signal`` column in
gold/ml_based_strategy/5m, computed by a logistic regression trained
in train.ipynb (saved to model.pkl in this folder).

Features = the last 5 5-minute returns. State is kept in a small
predictor object that gets warmed up by ``rebuild_from_silver`` at
startup, so the live stream emits non-null signals from bar 1.

"""
import asyncio
import pickle
import sys
from collections import deque
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import quantlake.gold.ingest as gold
from quantlake.bronze.connectors.binance_spot_rest import BinanceSpotOHLCVRestConnector
from quantlake.bronze.connectors.binance_spot_websocket import BinanceSpotOHLCVWebsocketConnector
from quantlake.live import run

GOLD_TABLE   = "ml_based_strategy"
TIMEFRAME    = "5m"
SYMBOL       = "BTCUSDT"
SILVER_TABLE = BinanceSpotOHLCVWebsocketConnector.TABLE_NAME
N_FEATURES   = 5
MODEL_PATH   = Path(__file__).parent / "model.pkl"

ws   = BinanceSpotOHLCVWebsocketConnector(timeframe="1m")
rest = BinanceSpotOHLCVRestConnector(timeframe="1m")


class MLPredictor:
    """Stateful predictor - keeps the last N+1 closes, returns predict_proba."""

    def __init__(self, model_path: Path, n: int):
        if not model_path.exists():
            raise FileNotFoundError(
                f"{model_path} not found, run train.ipynb in this folder first."
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


def transform_gold(gold_bar: pl.DataFrame, symbol: str) -> pl.DataFrame:
    """Add ml_signal = P(next close > current close) using the trained model.

    Works for both single-row (live) and multi-row (rebuild_from_silver) calls.
    First N+1 rows return null while the predictor warms up.
    """
    if gold_bar.is_empty():
        return gold_bar
    signals = [predictor.predict(float(c)) for c in gold_bar["close"].to_list()]
    return gold_bar.with_columns(pl.Series("ml_signal", signals, dtype=pl.Float64))


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

asyncio.run(run(
    ws_connector=ws,
    rest_connector=rest,
    symbols=[SYMBOL],
    gold_table=GOLD_TABLE,
    timeframe=TIMEFRAME,
    transform_gold=transform_gold,
))
