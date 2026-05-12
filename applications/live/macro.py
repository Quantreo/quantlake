"""End of v0.7.1 - Live gold build, macro (FX + T10Y2Y overlay).

Multi-instrument gold table. Currently EURUSD + GBPUSD, extend by adding
to SYMBOLS. Features go beyond simple MAs - ShannonEntropy and Skewness
over a 50-bar window showcase what Oryon does for statistical signals.

Two poll loops concurrently:
  - Capital.com every minute - primary. Feeds bronze/capitalcom_ohlcv +
    silver/macro_ohlcv, builds the 1h gold bar on each TF boundary.
  - FRED once an hour       - refreshes bronze/fred + silver/fred so the
    T10Y2Y join stays current (H.15 releases daily at ~16:30 ET).

transform_gold as-of-joins T10Y2Y onto the resampled 1h bar before features.

"""
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import polars as pl
from deltalake import DeltaTable
from oryon import FeaturePipeline
from oryon.features import Ema, ShannonEntropy, Skewness, Sma

import quantlake.bronze.ingest as bronze
import quantlake.gold.ingest as gold
import quantlake.poll as poll
import quantlake.silver.ingest as silver
from quantlake.bronze.connectors.capital_rest import CapitalComOHLCVRestConnector
from quantlake.bronze.connectors.fred import FREDConnector
from quantlake.config import SILVER_ROOT
from quantlake.silver import merge
from quantlake.silver.ohlcv import clean_ohlcv
from symbols import FRED_SERIES, MACRO_INSTRUMENTS

GOLD_TABLE   = "macro"
TIMEFRAME    = "1h"
MACRO_SERIES = FRED_SERIES[0]   # T10Y2Y - the overlay series for this gold
SYMBOLS      = ("EURUSD", "GBPUSD")
INSTS        = [i for i in MACRO_INSTRUMENTS if i.symbol in SYMBOLS]

capital = CapitalComOHLCVRestConnector(timeframe="1m")
fred    = FREDConnector()


def _join_macro(df_tf: pl.DataFrame, symbol:str) -> pl.DataFrame:
    """As-of join T10Y2Y onto the 1h frame + age column."""
    path = str(SILVER_ROOT / fred.TABLE_NAME)
    if not DeltaTable.is_deltatable(path):
        return df_tf
    macro = (
        pl.from_arrow(DeltaTable(path).to_pyarrow_table(
            filters=[("symbol", "=", MACRO_SERIES)],
            columns=["timestamp", "value"],
        ))
        .sort("timestamp")
        .rename({"timestamp": "macro_ts", "value": "t10y2y"})
    )
    return (
        df_tf.sort("timestamp")
        .join_asof(macro, left_on="timestamp", right_on="macro_ts", strategy="backward")
        .with_columns(
            ((pl.col("timestamp") - pl.col("macro_ts")).dt.total_seconds() / 3600.0)
            .alias("t10y2y_age_hours")
        )
        .drop("macro_ts")
    )


def make_pipeline() -> FeaturePipeline:
    """SMAs/EMAs on price + ShannonEntropy + Skewness on t10y2y overlay."""
    return FeaturePipeline(
        features=[
            Sma(["close"],  window=20, outputs=["close_sma_20"]),
            Ema(["close"],  window=20, outputs=["close_ema_20"]),
            ShannonEntropy(["t10y2y"], window=50, outputs=["t10y2y_entropy_50"]),
            Skewness(["t10y2y"], window=50, outputs=["t10y2y_skewness_50"]),
        ],
        input_columns=["close", "t10y2y"],
    )


# One pipeline per symbol - indicator state must not bleed across instruments.
pipelines: dict[str, FeaturePipeline] = {inst.symbol: make_pipeline() for inst in INSTS}


def _capital_tick() -> None:
    now = datetime.now(timezone.utc)
    for inst in INSTS:
        try:
            df = capital.fetch(symbol=inst.capital, start=now - timedelta(minutes=90), end=now)
        except Exception as e:
            print(f"[{inst.symbol}] capital fetch error: {e}")
            continue
        if df.is_empty():
            continue

        df = bronze.add_partition_columns(df, symbol=inst.symbol)
        bronze.save(df, capital.TABLE_NAME)
        merge.save_macro(clean_ohlcv(df))

        bar = gold.build_live_bar(
            silver_table=merge.MACRO_OHLCV,
            symbol=inst.symbol,
            gold_table=GOLD_TABLE,
            timeframe=TIMEFRAME,
            pipeline=pipelines[inst.symbol],
            transform_gold=_join_macro,
        )
        if bar is not None:
            print(bar)


def _fred_tick() -> None:
    now = datetime.now(timezone.utc)
    for series in FRED_SERIES:
        last = bronze.last_bronze_ts(fred.TABLE_NAME, series)
        start = last + timedelta(days=1) if last else now - timedelta(days=30)
        if start >= now:
            continue
        df = fred.fetch(symbol=series, start=start, end=now)
        if df.is_empty():
            continue
        df = bronze.add_partition_columns(df, symbol=series)
        bronze.save(df, fred.TABLE_NAME)
        silver.ingest(df, fred.TABLE_NAME)
        print(f"[fred] {series}: +{len(df)} obs")




print(f"Rebuilding gold/{GOLD_TABLE}/{TIMEFRAME} from silver...")
for inst in INSTS:
    built = gold.rebuild_from_silver(
        silver_table=merge.MACRO_OHLCV,
        symbol=inst.symbol,
        gold_table=GOLD_TABLE,
        timeframe=TIMEFRAME,
        pipeline=make_pipeline(),
        transform_gold=_join_macro,
    )
    rows = 0 if built is None else len(built)
    print(f"  {inst.symbol}: {rows:,} bars")
    gold.warmup_pipeline(pipelines[inst.symbol], GOLD_TABLE, TIMEFRAME, inst.symbol)

threading.Thread(
    target=poll.run,
    kwargs={"task": _fred_tick, "interval": "1h", "offset_ms": 500},
    daemon=True,
).start()

poll.run(task=_capital_tick, interval="1m", offset_ms=500)










