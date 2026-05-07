"""End of v0.6.3 - USDA NASS bootstrap (winter wheat planted acreage).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import quantlake.bronze.ingest as bronze
from quantlake.bronze.connectors.usda_nass import USDANassConnector
from symbols import WHEAT_STATES

COMMODITY = "WHEAT"
CLASS = "WINTER"
TABLE = USDANassConnector.TABLE_NAME

connector = USDANassConnector()

df = connector.fetch_planted(
    commodity=COMMODITY,
    class_desc=CLASS,
    states=list(WHEAT_STATES.keys()),
    year_start=2010,
    year_end=2026,
)

if df.is_empty():
    print("No NASS data returned")
else:
    symbol = f"{COMMODITY}_{CLASS}"
    df = bronze.add_partition_columns(df, symbol=symbol)
    bronze.save(df, TABLE)
    print(f"[{symbol}] {len(df):,} rows ingested ({len(WHEAT_STATES)} states x 15 years)")
