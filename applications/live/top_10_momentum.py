"""End of video 4.3 — first live strategy.

Live gold build for the top-10 crypto basket. Each incoming 1m bar from
Binance WebSocket goes through bronze → silver → (every 5 min) gold,
with SMA20 + EMA20 features computed bar-by-bar.

On startup: rebuild gold from all stored silver so features land with
proper warm-up before the live stream starts emitting bars.

Usage:
    poetry run python applications/live/top_10_momentum_crypto.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from oryon import FeaturePipeline
from oryon.features import Ema, Sma

import quantlake.gold.ingest as gold
from quantlake.bronze.connectors.binance_spot_rest import BinanceSpotOHLCVRestConnector
from quantlake.bronze.connectors.binance_spot_websocket import BinanceSpotOHLCVWebsocketConnector
from quantlake.live import run
from symbols import TOP10

GOLD_TABLE = "top_10_momentum_crypto"
TIMEFRAME = "5m"
SILVER_TABLE = BinanceSpotOHLCVWebsocketConnector.TABLE_NAME  # binance_spot_ohlcv

ws = BinanceSpotOHLCVWebsocketConnector(timeframe="1m")
rest = BinanceSpotOHLCVRestConnector(timeframe="1m")


def make_pipeline() -> FeaturePipeline:
    return FeaturePipeline(
        features=[
            Sma(["close"], window=20, outputs=["close_sma_20"]),
            Ema(["close"], window=20, outputs=["close_ema_20"]),
        ],
        input_columns=["close"],
    )


# One pipeline per symbol for the LIVE path — indicator state must not
# bleed across instruments.
pipelines = {s: make_pipeline() for s in TOP10}


# Historical gold rebuild — fresh pipeline per symbol so batch state
# doesn't contaminate the live pipelines above.
print(f"Rebuilding gold/{GOLD_TABLE}/{TIMEFRAME} from silver…")
for symbol in TOP10:
    built = gold.rebuild_from_silver(
        silver_table=SILVER_TABLE,
        symbol=symbol,
        gold_table=GOLD_TABLE,
        timeframe=TIMEFRAME,
        pipeline=make_pipeline(),
    )
    rows = 0 if built is None else len(built)
    print(f"  {symbol}: {rows:,} bars")



asyncio.run(run(
    ws_connector=ws,
    rest_connector=rest,
    symbols=TOP10,
    gold_table=GOLD_TABLE,
    timeframe=TIMEFRAME,
    pipelines=pipelines,
))









