"""Same as binance_spot_ohlcv.py, but using the shared ingest pipeline.

The connector handles HTTP/pagination/normalization, and `ingest` takes
care of partition columns + idempotent upsert into the bronze Delta table.
"""
from datetime import datetime, UTC

import polars as pl
from deltalake import DeltaTable

from quantlake.config import BRONZE_ROOT
from quantlake.bronze.ingest import ingest
from quantlake.bronze.connectors.binance_spot_rest import BinanceSpotOHLCVRestConnector


connector = BinanceSpotOHLCVRestConnector(timeframe="1m")

df = ingest(
    connector,
    symbol="BTCUSDT",
    start=datetime(2025, 5, 17, tzinfo=UTC),
    end=datetime(2025, 5, 18, tzinfo=UTC),
)

print("Ingested:")
print(df)

table_path = str(BRONZE_ROOT / connector.TABLE_NAME)
stored = pl.from_arrow(DeltaTable(table_path).to_pyarrow_table()).sort("timestamp")

print(f"\nStored at {table_path}:")
print(stored)
