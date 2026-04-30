"""End of video 2.2 — historical bootstrap for Binance top-10 spot OHLCV.

Bulk archives cover up to the last complete month; REST fills the
current (incomplete) month. Re-running is safe — Delta merges on
(symbol, timestamp), bulk and REST share the same schema.

Note: silver.ingest is NOT called here yet. The silver layer is
introduced in Module 3.1 — this script will be amended at v3.1 to add
the pass-through to silver. Until then, only bronze is populated.

Usage:
    poetry run python applications/historical/binance.py
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import quantlake.bronze.ingest as bronze
from quantlake.bronze.connectors.binance_spot_bulk import BinanceSpotOHLCVBulkConnector
from quantlake.bronze.connectors.binance_spot_rest import BinanceSpotOHLCVRestConnector
from symbols import TOP10


BULK_START = datetime(2024, 1, 1, tzinfo=timezone.utc)

bulk = BinanceSpotOHLCVBulkConnector(timeframe="1m")
rest = BinanceSpotOHLCVRestConnector(timeframe="1m")


def _ingest(symbol: str) -> None:
    now = datetime.now(timezone.utc)
    bulk_end = datetime(now.year, now.month, 1, tzinfo=timezone.utc) - timedelta(microseconds=1)
    rest_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)

    print(f"[{symbol}] bulk {BULK_START.date()} → {bulk_end.date()}")
    df = bronze.ingest(bulk, symbol=symbol, start=BULK_START, end=bulk_end)
    print(f"[{symbol}]   bulk → {len(df):,} rows")

    print(f"[{symbol}] REST {rest_start.date()} → now")
    df = bronze.ingest(rest, symbol=symbol, start=rest_start, end=now)
    print(f"[{symbol}]   REST → {len(df):,} rows")


for s in TOP10:
    try:
        _ingest(s)
    except Exception as e:
        print(f"[{s}] ERROR: {e}")
print("\nDone.")