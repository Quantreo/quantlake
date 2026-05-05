"""End of v0.5.1 - Quick look at the Capital REST connector.

Twelve-line usage demo. Fetches one day of EURUSD 1-minute bars,
prints the row count, the first rows, and the schema. Useful right
after writing the connector to confirm the canonical schema (mid +
spread, UTC timestamps).

Run:
    poetry run python examples/bronze/capital_rest_minimal.py
"""
from datetime import datetime, timedelta, timezone

from quantlake.bronze.connectors.capital_rest import CapitalComOHLCVRestConnector
from dotenv import load_dotenv

load_dotenv()

connector = CapitalComOHLCVRestConnector(timeframe="1m")

now = datetime.now(timezone.utc)
df = connector.fetch(symbol="EURUSD", start=now - timedelta(days=1), end=now)

print(f"{len(df):,} rows")
print(df.head())
print(df.schema)
