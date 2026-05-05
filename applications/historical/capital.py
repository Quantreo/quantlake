"""End of v0.5.1 - Capital.com REST historical bootstrap.

Walks through MACRO_INSTRUMENTS, resumes from last_bronze_ts, fetches
the gap, partitions and saves.

Run:
    poetry run python applications/historical/capital.py
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import quantlake.bronze.ingest as bronze
from quantlake.bronze.connectors.capital_rest import CapitalComOHLCVRestConnector
from symbols import MACRO_INSTRUMENTS

CAPITAL_START = datetime(2026, 5, 3, tzinfo=timezone.utc)
TABLE = CapitalComOHLCVRestConnector.TABLE_NAME

connector = CapitalComOHLCVRestConnector(timeframe="1m")
now = datetime.now(timezone.utc)

for inst in MACRO_INSTRUMENTS:
    last = bronze.last_bronze_ts(TABLE, inst.symbol)
    start = last + timedelta(minutes=1) if last else CAPITAL_START
    if start >= now:
        print(f"[{inst.symbol}] up to date")
        continue

    df = connector.fetch(symbol=inst.capital, start=start, end=now)
    if df.is_empty():
        continue

    df = bronze.add_partition_columns(df, symbol=inst.symbol)
    bronze.save(df, TABLE)
    print(f"[{inst.symbol}] {len(df):,} rows")