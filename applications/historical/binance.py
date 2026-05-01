"""End of video 3.1 — historical bootstrap modified to populate silver.

Two lines added vs v0.2.2 (one after each bronze.ingest):
    silver.ingest(df, TABLE)

Now both bronze AND silver are populated by the bootstrap. Re-running
is still safe — both layers merge on (symbol, timestamp).
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import quantlake.bronze.ingest as bronze
import quantlake.silver.ingest as silver

from quantlake.bronze.connectors.binance_spot_bulk import BinanceSpotOHLCVBulkConnector
from quantlake.bronze.connectors.binance_spot_rest import BinanceSpotOHLCVRestConnector
from symbols import TOP10


BULK_START = datetime(2017, 2, 1, tzinfo=timezone.utc)
TABLE = BinanceSpotOHLCVBulkConnector.TABLE_NAME

bulk = BinanceSpotOHLCVBulkConnector(timeframe="1m")
rest = BinanceSpotOHLCVRestConnector(timeframe="1m")


def _ingest(symbol: str) -> None:
    now = datetime.now(timezone.utc)
    bulk_end = datetime(now.year, now.month, 1, tzinfo=timezone.utc) - timedelta(microseconds=1)
    rest_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)

    print(f"[{symbol}] bulk {BULK_START.date()} → {bulk_end.date()}")
    df = bronze.ingest(bulk, symbol=symbol, start=BULK_START, end=bulk_end)
    df_clean = silver.ingest(df, TABLE)
    print(f"[{symbol}]   bulk → {len(df):,} rows")

    print(f"[{symbol}] REST {rest_start.date()} → now")
    df = bronze.ingest(rest, symbol=symbol, start=rest_start, end=now)
    df_clean = silver.ingest(df, TABLE)
    print(f"[{symbol}]   REST → {len(df):,} rows")


for s in TOP10:
    try:
        _ingest(s)
    except Exception as e:
        print(f"[{s}] ERROR: {e}")
print("\nDone.")