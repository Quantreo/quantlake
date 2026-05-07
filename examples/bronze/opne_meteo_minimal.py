"""End of v0.6.2 - Quick look at the Open-Meteo connector.

"""
from datetime import datetime, timezone

from quantlake.bronze.connectors.open_meteo import OpenMeteoConnector

connector = OpenMeteoConnector(latitude=38.5, longitude=-98.0)

df = connector.fetch(
    symbol="KS",
    start=datetime(2026, 4, 1, tzinfo=timezone.utc),
    end=datetime(2026, 4, 30, tzinfo=timezone.utc),
)

print(f"{len(df):,} daily observations")
print(df.head())
print(df.schema)
