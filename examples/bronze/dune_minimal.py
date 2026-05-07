"""End of v0.6.4 - Quick look at the Dune connector.

"""
from datetime import datetime, timedelta, timezone

from quantlake.bronze.connectors.dune import DuneQueryConnector
from dotenv import load_dotenv

load_dotenv()

connector = DuneQueryConnector(
    query_id=7445139,
    table_name="dune_eth_gas",
    timestamp_col="timestamp_1h",
    rename={
        "open_gwei":  "open",
        "high_gwei":  "high",
        "low_gwei":   "low",
        "close_gwei": "close",
    },
)

now = datetime.now(timezone.utc)
df = connector.fetch(
    symbol="ETH",
    start=now - timedelta(days=30),
    end=now,
)

print(f"{len(df):,} hourly bars")
print(df.head())
print(df.schema)
