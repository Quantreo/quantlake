"""End of v0.6.1 - FRED historical bootstrap.

Walks through FRED_SERIES, resumes from last_bronze_ts, fetches the
gap, partitions and saves.

Run:
    poetry run python applications/historical/fred.py
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import quantlake.bronze.ingest as bronze
import quantlake.silver.ingest as silver
from quantlake.bronze.connectors.fred import FREDConnector

sys.path.insert(0, str(Path(__file__).parent.parent))
from symbols import FRED_SERIES


from dotenv import load_dotenv

load_dotenv()


FRED_START = datetime(2010, 1, 1, tzinfo=timezone.utc)
TABLE = FREDConnector.TABLE_NAME

connector = FREDConnector(release_time_et="16:30")
now = datetime.now(timezone.utc)

for series in FRED_SERIES:
    start = FRED_START
    if start >= now:
        print(f"[{series}] up to date")
        continue

    df = connector.fetch(symbol=series, start=start, end=now)
    if df.is_empty():
        continue

    df = bronze.add_partition_columns(df, symbol=series)
    bronze.save(df, TABLE)
    silver.ingest(df, TABLE)
    print(f"[{series}] {len(df):,} observations")
