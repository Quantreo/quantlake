"""End of v0.6.2 - Open-Meteo historical bootstrap for the 10 US wheat states.

Writes bronze/open_meteo + silver/crop_weather. One connector instance
per state (lat/lon centroids of agricultural areas).

Run:
    poetry run python applications/historical/weather.py
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import quantlake.bronze.ingest as bronze
from quantlake.bronze.connectors.open_meteo import OpenMeteoConnector
import quantlake.silver.ingest as silver
from quantlake.silver.ohlcv import clean_ohlcv
from symbols import WHEAT_STATES
import time
WEATHER_START = datetime(2010, 1, 1, tzinfo=timezone.utc)
TABLE = OpenMeteoConnector.TABLE_NAME

now = datetime.now(timezone.utc)

for state, (lat, lon) in WHEAT_STATES.items():
    connector = OpenMeteoConnector(latitude=lat, longitude=lon)
    df = connector.fetch(symbol=state, start=WEATHER_START, end=now)
    if df.is_empty():
        continue

    df = bronze.add_partition_columns(df, symbol=state)
    bronze.save(df, TABLE)
    silver.save(clean_ohlcv(df), TABLE)
    print(f"[{state}] {len(df):,} daily observations")

    time.sleep(5)
