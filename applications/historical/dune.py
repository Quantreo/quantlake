"""End of v0.6.4 - Dune historical bootstrap (ETH gas hourly OHLC).

Run:
    poetry run python applications/historical/dune.py
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import quantlake.bronze.ingest as bronze
from quantlake.bronze.connectors.dune import DuneQueryConnector
from dotenv import load_dotenv

load_dotenv()

# Replace with your own Dune query_id (saved on dune.com).
# The query should select hourly OHLC of gas with columns
# {time, open_gwei, high_gwei, low_gwei, close_gwei}.
QUERY_ID = 7445139
TABLE = "dune_eth_gas"
SYMBOL = "ETH"

connector = DuneQueryConnector(
    query_id=QUERY_ID,
    table_name=TABLE,
    timestamp_col="timestamp_1h",
    rename={
        "open_gwei":  "open",
        "high_gwei":  "high",
        "low_gwei":   "low",
        "close_gwei": "close",
    },
)

last = bronze.last_bronze_ts(TABLE, SYMBOL)
start = last + timedelta(hours=1) if last else datetime(2020, 1, 1, tzinfo=timezone.utc)
now = datetime.now(timezone.utc)

if start >= now:
    print(f"[{SYMBOL}] up to date")
else:
    df = connector.fetch(symbol=SYMBOL, start=start, end=now)
    if not df.is_empty():
        df = bronze.add_partition_columns(df, symbol=SYMBOL)
        bronze.save(df, TABLE)
        print(f"[{SYMBOL}] {len(df):,} rows ingested")












