"""End of v0.7.2 - Live gold build, wheat_stress (1d WHEAT CFD + NASS-weighted rain stress).

We don't pre-cook a silver/crop_weather in M6.2 - we just have raw daily
weather in bronze/open_meteo per US wheat state. M7.2 does the whole
composition inline:

  1. Read bronze/open_meteo for WHEAT_STATES.
  2. Compute per-state stress as (baseline - precip_30d) / baseline,
     where baseline = each state's full-history mean of precip_30d.
     Positive stress = drier than usual = drought risk.
  3. Vintage-safe join_asof on NASS planted_acres per state (no
     look-ahead on agricultural releases).
  4. National weighted average = sum(stress * acres) / sum(acres),
     grouped by date. Heavier weight to bigger planted states.
  5. Left-join the national stress_index onto the 1d WHEAT CFD bar.

Two poll loops concurrently:
  - Capital.com every minute - primary. Builds the 1d WHEAT gold bar.
  - Open-Meteo every hour    - refreshes bronze/open_meteo per state.

Run the matching historical scripts at least once:
    applications/historical/capital.py        -> bronze/capitalcom_ohlcv WHEAT
    applications/historical/macro_silver.py   -> silver/macro_ohlcv WHEAT
    applications/historical/weather.py        -> bronze/open_meteo per state
    applications/historical/nass.py           -> silver/usda_nass_planted

Usage:
    poetry run python applications/live/wheat_stress.py
"""
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
from quantlake.bronze.connectors.capital_rest import CapitalComOHLCVRestConnector
from quantlake.bronze.connectors.open_meteo import OpenMeteoConnector
from quantlake.config import BRONZE_ROOT, SILVER_ROOT
from quantlake.silver import merge
from quantlake.silver.ohlcv import clean_ohlcv
from symbols import MACRO_INSTRUMENTS, WHEAT_STATES

GOLD_TABLE     = "wheat_stress"
TIMEFRAME      = "1d"
WEATHER_TABLE  = "open_meteo"
NASS_TABLE     = "usda_nass_planted"

# This strat-level convention (NASS filter targets winter wheat CFD).
WHEAT_SYMBOL    = "WHEAT"
WHEAT_COMMODITY = "WHEAT"
WHEAT_CLASS     = "WINTER"

WHEAT_INST = next(i for i in MACRO_INSTRUMENTS if i.symbol == WHEAT_SYMBOL)
capital    = CapitalComOHLCVRestConnector(timeframe="1m")


# One Open-Meteo connector per wheat state - lat/lon bound at construction.
METEO = {
    code: OpenMeteoConnector(latitude=lat, longitude=lon)
    for code, (lat, lon) in WHEAT_STATES.items()
}


# Per-state stress: rolling rain vs that state's historical baseline.

def _compute_state_stress() -> pl.DataFrame | None:
    """Read bronze/open_meteo for WHEAT_STATES and derive a daily
    `stress` column per state.

    Formula: 30-day rolling precipitation vs the state's full-history
    mean of precip_30d. Sign inverted so positive = drier than usual.
    Simple, no day-of-year climatology - kept readable on purpose.
    """
    path = str(BRONZE_ROOT / WEATHER_TABLE)
    if not DeltaTable.is_deltatable(path):
        return None
    df = pl.from_arrow(DeltaTable(path).to_pyarrow_table()).filter(
        pl.col("symbol").is_in(list(WHEAT_STATES))
    )
    if df.is_empty():
        return None

    df = df.sort(["symbol", "timestamp"]).with_columns(
        pl.col("precip").rolling_sum(window_size=30).over("symbol").alias("precip_30d"),
    )
    df = df.with_columns(
        pl.col("precip_30d").mean().over("symbol").alias("precip_30d_baseline"),
    ).with_columns(
        ((pl.col("precip_30d_baseline") - pl.col("precip_30d")) / pl.col("precip_30d_baseline"))
        .alias("stress"),
    )
    return df.select(["timestamp", pl.col("symbol").alias("state"), "stress"]).drop_nulls("stress")


def _load_weights() -> pl.DataFrame | None:
    path = str(SILVER_ROOT / NASS_TABLE)
    if not DeltaTable.is_deltatable(path):
        return None
    df = pl.from_arrow(DeltaTable(path).to_pyarrow_table()).filter(
        (pl.col("commodity") == WHEAT_COMMODITY)
        & (pl.col("class_desc") == WHEAT_CLASS)
        & (pl.col("state").is_in(list(WHEAT_STATES)))
    )
    return df.select("timestamp", "state", "planted_acres").sort(["state", "timestamp"]) \
        if not df.is_empty() else None


def _national_stress_frame() -> pl.DataFrame | None:
    """One row per UTC day with the NASS-weighted national stress_index.

    Vintage-safe: planted_acres are join_asof'd per state with
    strategy='backward', so each (date, state) only sees NASS releases
    already published on that date. No look-ahead.
    """
    stress = _compute_state_stress()
    weights = _load_weights()
    if stress is None or weights is None:
        return None

    per_state = (
        stress.sort(["state", "timestamp"])
        .join_asof(weights, on="timestamp", by="state", strategy="backward")
        .drop_nulls(["planted_acres", "stress"])
    )
    if per_state.is_empty():
        return None

    return (
        per_state.group_by("timestamp")
        .agg(
            ((pl.col("stress") * pl.col("planted_acres")).sum()
             / pl.col("planted_acres").sum()).alias("stress_index"),
            pl.col("planted_acres").sum().alias("total_acres"),
            pl.col("state").n_unique().alias("n_states"),
        )
        .sort("timestamp")
    )


def _join_stress(df_tf: pl.DataFrame, symbol: str) -> pl.DataFrame:
    national = _national_stress_frame()
    if national is None:
        return df_tf.with_columns(
            pl.lit(None).cast(pl.Float64).alias("stress_index"),
            pl.lit(None).cast(pl.Float64).alias("total_acres"),
            pl.lit(None).cast(pl.Int64).alias("n_states"),
        )
    return df_tf.sort("timestamp").join(national, on="timestamp", how="left")


def make_pipeline() -> FeaturePipeline:
    return FeaturePipeline(
        features=[
            Sma(["close"],        window=20, outputs=["close_sma_20"]),
            Ema(["close"],        window=20, outputs=["close_ema_20"]),
            Sma(["stress_index"], window=30, outputs=["stress_sma_30"]),
        ],
        input_columns=["close", "stress_index"],
    )


pipeline = make_pipeline()


# Capital tick: pull WHEAT, update silver, attempt gold build

def _capital_tick() -> None:
    now = datetime.now(timezone.utc)
    try:
        df = capital.fetch(symbol=WHEAT_INST.capital, start=now - timedelta(minutes=90), end=now)
    except Exception as e:
        print(f"[{WHEAT_SYMBOL}] capital fetch error: {e}")
        return
    if df.is_empty():
        return

    df = bronze.add_partition_columns(df, symbol=WHEAT_SYMBOL)
    bronze.save(df, capital.TABLE_NAME)
    merge.save_macro(clean_ohlcv(df))

    bar = gold.build_live_bar(
        silver_table=merge.MACRO_OHLCV,
        symbol=WHEAT_SYMBOL,
        gold_table=GOLD_TABLE,
        timeframe=TIMEFRAME,
        pipeline=pipeline,
        transform_gold=_join_stress,
    )
    if bar is not None:
        print(bar)


# Open-Meteo tick: refresh bronze for every state

def _open_meteo_tick() -> None:
    for code, conn in METEO.items():
        try:
            snap = conn.snapshot(past_days=3, forecast_days=0)
        except Exception as e:
            print(f"[{code}] open-meteo snapshot error: {e}")
            continue
        if snap.is_empty():
            continue
        snap = bronze.add_partition_columns(snap, symbol=code)
        bronze.save(snap, OpenMeteoConnector.TABLE_NAME)
    print(f"[weather] bronze refreshed for {len(METEO)} states")


print(f"Rebuilding gold/{GOLD_TABLE}/{TIMEFRAME} from silver...")
built = gold.rebuild_from_silver(
    silver_table=merge.MACRO_OHLCV,
    symbol=WHEAT_SYMBOL,
    gold_table=GOLD_TABLE,
    timeframe=TIMEFRAME,
    pipeline=make_pipeline(),
    transform_gold=_join_stress,
)
rows = 0 if built is None else len(built)
print(f"  {WHEAT_SYMBOL}: {rows:,} bars")

gold.warmup_pipeline(pipeline, GOLD_TABLE, TIMEFRAME, WHEAT_SYMBOL)

threading.Thread(
    target=poll.run,
    kwargs={"task": _open_meteo_tick, "interval": "1h", "offset_ms": 500},
    daemon=True,
).start()

poll.run(task=_capital_tick, interval="1m", offset_ms=500)








