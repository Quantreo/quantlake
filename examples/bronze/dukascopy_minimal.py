"""End of v0.5.3 - Quick look at the Dukascopy connector.

Twelve-line usage demo. Fetches one day of EURUSD 1-minute bars,
prints the row count, the first rows, and the schema.

Run:
    poetry run python examples/bronze/dukascopy_minimal.py
"""
from datetime import datetime, timezone

from quantlake.bronze.connectors.dukascopy import DukascopyOHLCVConnector

connector = DukascopyOHLCVConnector(price_scale=100_000.0)

df = connector.fetch(
    symbol="EURUSD",
    start=datetime(2025, 1, 15, tzinfo=timezone.utc),
    end=datetime(2025, 1, 16, tzinfo=timezone.utc),
)

print(f"{len(df):,} rows")
print(df.head())
print(df.schema)
