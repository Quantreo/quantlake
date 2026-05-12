"""End of v0.7.3 - Live gold build, eth_data (ETHUSDT OHLCV + ETH gas overlay).

Two feeds running concurrently:
  - Binance WebSocket ETHUSDT 1m - primary, drives the 1h gold build.
  - Owlracle snapshot poll every minute - persists one gas sample per
    minute to bronze/owlracle_eth_gas; at each tick, if the previous
    hour isn't in silver/eth_gas yet, resamples those samples into
    one OHLC bar and upserts silver/eth_gas.

Why not use Owlracle /history? The endpoint is paid and silently hangs
when the key has no credit. The free /gas endpoint only exposes a
current-instant snapshot - so we build our own hourly history from
snapshots. Deep historical gas is still available via Dune (free
with a Dune key), which writes into the same silver/eth_gas.

transform_gold as-of-joins silver/eth_gas onto the 1h frame.

"""
import asyncio
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import polars as pl
from deltalake import DeltaTable
from oryon import FeaturePipeline
from oryon.features import Ema, Sma

import quantlake.bronze.ingest as bronze
import quantlake.gold.ingest as gold
import quantlake.poll as poll
from quantlake.bronze.connectors.binance_spot_rest import BinanceSpotOHLCVRestConnector
from quantlake.bronze.connectors.binance_spot_websocket import BinanceSpotOHLCVWebsocketConnector
from quantlake.bronze.connectors.owlracle_gas import OwlracleGasConnector
from quantlake.config import BRONZE_ROOT, SILVER_ROOT
from quantlake.live import run
from quantlake.silver import merge
from quantlake.silver.ohlcv import clean_ohlcv

GOLD_TABLE     = "eth_data"
TIMEFRAME      = "1h"
ETH_SYMBOL     = "ETHUSDT"       # Binance silver
ETH_GAS_SYMBOL = "ETH"           # Owlracle + Dune silver/eth_gas

ws   = BinanceSpotOHLCVWebsocketConnector(timeframe="1m")
rest = BinanceSpotOHLCVRestConnector(timeframe="1m")
owl  = OwlracleGasConnector(network="eth")

SILVER_GAS_PATH = str(SILVER_ROOT / merge.ETH_GAS)
BRONZE_OWL_PATH = str(BRONZE_ROOT / owl.TABLE_NAME)


def _join_gas(df_tf: pl.DataFrame, symbol: str) -> pl.DataFrame:
    """As-of join silver/eth_gas OHLC onto the 1h ETH frame."""
    if not DeltaTable.is_deltatable(SILVER_GAS_PATH):
        return df_tf
    gas = (
        pl.from_arrow(DeltaTable(SILVER_GAS_PATH).to_pyarrow_table())
        .sort("timestamp")
        .select(
            "timestamp",
            pl.col("open").alias("gas_open"),
            pl.col("high").alias("gas_high"),
            pl.col("low").alias("gas_low"),
            pl.col("close").alias("gas_close"),
        )
    )
    return df_tf.sort("timestamp").join_asof(gas, on="timestamp", strategy="backward")


def _last_eth_gas_silver_ts() -> datetime | None:
    if not DeltaTable.is_deltatable(SILVER_GAS_PATH):
        return None
    df = pl.from_arrow(DeltaTable(SILVER_GAS_PATH).to_pyarrow_table(
        filters=[("symbol", "=", ETH_GAS_SYMBOL)], columns=["timestamp"],
    ))
    return df["timestamp"].max() if not df.is_empty() else None


def _build_hour_bar_from_bronze(hour_open: datetime) -> None:
    """Resample bronze samples in [hour_open, hour_open+1h) into one
    OHLC silver/eth_gas row. No-op if no samples landed in that window.
    """
    if not DeltaTable.is_deltatable(BRONZE_OWL_PATH):
        return
    samples = (
        pl.from_arrow(DeltaTable(BRONZE_OWL_PATH).to_pyarrow_table(
            filters=[("symbol", "=", ETH_GAS_SYMBOL)], columns=["timestamp", "price"],
        ))
        .filter(
            (pl.col("timestamp") >= hour_open)
            & (pl.col("timestamp") < hour_open + timedelta(hours=1))
        )
        .sort("timestamp")
    )
    if samples.is_empty():
        return

    prices = samples["price"]
    bar = pl.DataFrame({
        "timestamp": pl.Series([hour_open],    dtype=pl.Datetime("us", "UTC")),
        "open":      pl.Series([prices[0]],    dtype=pl.Float64),
        "high":      pl.Series([prices.max()], dtype=pl.Float64),
        "low":       pl.Series([prices.min()], dtype=pl.Float64),
        "close":     pl.Series([prices[-1]],   dtype=pl.Float64),
    })
    bar = bronze.add_partition_columns(bar, symbol=ETH_GAS_SYMBOL)
    merge.save_eth_gas(clean_ohlcv(bar))
    print(f"[owl] built 1h bar {hour_open} from {len(samples)} samples")


def _owl_tick() -> None:
    """Snapshot -> bronze, then if the previous hour isn't in silver yet,
    bake it from bronze samples.
    """
    snap = owl.snapshot()
    if snap.is_empty():
        return
    snap = bronze.add_partition_columns(snap, symbol=ETH_GAS_SYMBOL)
    bronze.save(snap, owl.TABLE_NAME)

    hour_open = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    last_silver = _last_eth_gas_silver_ts()
    if last_silver is None or last_silver < hour_open:
        _build_hour_bar_from_bronze(hour_open)


def make_pipeline() -> FeaturePipeline:
    return FeaturePipeline(
        features=[
            Sma(["close"], window=20, outputs=["close_sma_20"]),
            Ema(["close"], window=20, outputs=["close_ema_20"]),
        ],
        input_columns=["close"],
    )


print(f"Rebuilding gold/{GOLD_TABLE}/{TIMEFRAME} from silver...")
built = gold.rebuild_from_silver(
    silver_table=ws.TABLE_NAME,
    symbol=ETH_SYMBOL,
    gold_table=GOLD_TABLE,
    timeframe=TIMEFRAME,
    pipeline=make_pipeline(),
    transform_gold=_join_gas,
)
rows = 0 if built is None else len(built)
print(f"  {ETH_SYMBOL}: {rows:,} bars")

# Owlracle poll runs in a background thread so the main event loop
# stays free for the Binance WebSocket.
threading.Thread(
    target=poll.run,
    kwargs={"task": _owl_tick, "interval": "1m", "offset_ms": 500},
    daemon=True,
).start()

asyncio.run(run(
    ws_connector=ws,
    rest_connector=rest,
    symbols=[ETH_SYMBOL],
    gold_table=GOLD_TABLE,
    timeframe=TIMEFRAME,
    pipelines={ETH_SYMBOL: make_pipeline()},
    transform_gold=_join_gas,
))



