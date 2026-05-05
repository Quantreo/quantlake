"""End of v0.5.3 - Dukascopy historical bootstrap.

Writes bronze/dukascopy_ohlcv only. Flat, no helpers, no try/except.
Resumable via last_bronze_ts. Skips instruments without a Dukascopy
code (e.g. WHEAT, lives on Capital only).

Usage:
    poetry run python applications/historical/dukascopy.py
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import quantlake.bronze.ingest as bronze
from quantlake.bronze.connectors.dukascopy import DukascopyOHLCVConnector
from symbols import MACRO_INSTRUMENTS

DUKA_START = datetime(2026, 1, 1, tzinfo=timezone.utc)
TABLE = DukascopyOHLCVConnector.TABLE_NAME

now = datetime.now(timezone.utc)
end = (now - timedelta(days=1)).replace(hour=23, minute=59, second=0, microsecond=0)

for inst in MACRO_INSTRUMENTS:
    if not inst.duka:
        print(f"[{inst.symbol}] no Dukascopy code - skip")
        continue

    last = bronze.last_bronze_ts(TABLE, inst.symbol)
    start = last + timedelta(minutes=1) if last else DUKA_START
    if start >= end:
        print(f"[{inst.symbol}] up to date")
        continue

    connector = DukascopyOHLCVConnector(price_scale=inst.price_scale)
    df = connector.fetch(symbol=inst.duka, start=start, end=end)
    if df.is_empty():
        continue

    df = bronze.add_partition_columns(df, symbol=inst.symbol)
    bronze.save(df, TABLE)
    print(f"[{inst.symbol}] {len(df):,} rows")
