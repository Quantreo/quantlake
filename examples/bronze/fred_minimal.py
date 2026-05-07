"""End of v0.6.1 - Quick look at the FRED connector.

Fetches 30 days of DGS10 (10-Year Treasury Yield) and prints the
DataFrame head plus schema. Useful right after writing the connector
to confirm the canonical schema (timestamp at release time UTC, value
as Float64 with NaN for missing days).

Run:
    poetry run python examples/bronze/fred_minimal.py
"""
from datetime import datetime, timedelta, timezone

from quantlake.bronze.connectors.fred import FREDConnector

from dotenv import load_dotenv

load_dotenv()

connector = FREDConnector(release_time_et="16:30")

now = datetime.now(timezone.utc)
df = connector.fetch(
    symbol="DGS10",
    start=now - timedelta(days=30),
    end=now,
)

print(f"{len(df):,} observations")
print(df.head())
print(df.schema)
