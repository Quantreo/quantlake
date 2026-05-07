"""End of v0.6.3 - Quick look at the USDA NASS connector.
"""

from quantlake.bronze.connectors.usda_nass import USDANassConnector
from dotenv import load_dotenv

load_dotenv()

connector = USDANassConnector()

df = connector.fetch_planted(
    commodity="WHEAT",
    class_desc="WINTER",
    states=["KS", "OK", "TX"],
    year_start=2020,
    year_end=2024,
)

print(f"{len(df):,} rows")
print(df.head())
print(df.schema)
