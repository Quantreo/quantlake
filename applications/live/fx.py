"""End of v0.5.5 - Live FX gold build via poll.run + Capital REST.

First non-Binance live application. Reads from silver/macro_ohlcv (the
composite silver built in v0.5.4 by historical/macro_silver.py), so the
rebuild_from_silver call returns ~5 years of pre-aligned history. Each
minute, fetches the last 90 minutes from Capital, updates bronze +
silver via merge.save_macro, and tries to emit the just-closed 1h gold
bar with SMA20 + EMA20.

Dukascopy is NOT updated live - it's our deep historical anchor, frozen
end-of-day. Capital provides the live feed on top of the composite
silver.

Usage:
    poetry run python applications/live/fx.py
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from oryon import FeaturePipeline
from oryon.features import Ema, Sma

import quantlake.bronze.ingest as bronze
import quantlake.gold.ingest as gold
import quantlake.poll as poll
from quantlake.bronze.connectors.capital_rest import CapitalComOHLCVRestConnector
from quantlake.silver import merge
from quantlake.silver.ohlcv import clean_ohlcv
from symbols import MACRO_INSTRUMENTS

GOLD_TABLE = "fx"
TIMEFRAME = "1h"
SILVER_TABLE = merge.MACRO_OHLCV   # composite silver from v0.5.4

# FX subset of MACRO_INSTRUMENTS.
SYMBOLS = ("EURUSD", "GBPUSD")
INSTS = [i for i in MACRO_INSTRUMENTS if i.symbol in SYMBOLS]

capital = CapitalComOHLCVRestConnector(timeframe="1m")


def make_pipeline() -> FeaturePipeline:
    return FeaturePipeline(
        features=[
            Sma(["close"], window=20, outputs=["close_sma_20"]),
            Ema(["close"], window=20, outputs=["close_ema_20"]),
        ],
        input_columns=["close"],
    )


# One pipeline per symbol - indicator state must not bleed across instruments.
pipelines = {inst.symbol: make_pipeline() for inst in INSTS}


def fetch_capital_minute() -> None:
    """Fetch the last 90 min from Capital, write bronze + composite silver,
    try to emit the just-closed 1h gold bar per symbol.

    The 90-min sliding window gives resilience to dropped ticks; Delta
    merge on (symbol, timestamp) dedupes the overlap.
    """
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
            silver_table=SILVER_TABLE,
            symbol=inst.symbol,
            gold_table=GOLD_TABLE,
            timeframe=TIMEFRAME,
            pipeline=pipelines[inst.symbol],
        )
        if bar is not None:
            print(bar)


# Sync Capital bronze + silver via 7-day sliding window. Re-fetches always
# overlap so any internal gap left by past live ticks gets filled. Delta merge
# dedupes - existing minutes are no-op, missing minutes are inserted.
print("Syncing Capital bronze + silver...")
SYNC_DAYS = 7
sync_now = datetime.now(timezone.utc)
sync_start = sync_now - timedelta(days=SYNC_DAYS)
for inst in INSTS:
    df = capital.fetch(symbol=inst.capital, start=sync_start, end=sync_now)
    if df.is_empty():
        continue
    df = bronze.add_partition_columns(df, symbol=inst.symbol)
    bronze.save(df, capital.TABLE_NAME)
    merge.save_macro(clean_ohlcv(df))
    print(f"  {inst.symbol}: {len(df):,} bars synced")



# Historical rebuild per symbol from the composite silver.
print(f"Rebuilding gold/{GOLD_TABLE}/{TIMEFRAME} from silver...")
for inst in INSTS:
    built = gold.rebuild_from_silver(
        silver_table=SILVER_TABLE,
        symbol=inst.symbol,
        gold_table=GOLD_TABLE,
        timeframe=TIMEFRAME,
        pipeline=make_pipeline(),
    )
    rows = 0 if built is None else len(built)
    print(f"  {inst.symbol}: {rows:,} bars")

# Re-prime the live pipelines from the gold we just rebuilt.
for inst in INSTS:
    gold.warmup_pipeline(pipelines[inst.symbol], GOLD_TABLE, TIMEFRAME, inst.symbol)

poll.run(fetch_capital_minute, interval="1m", offset_ms=500)









