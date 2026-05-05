import polars as pl
from deltalake import DeltaTable

PATH = "data/gold/fx/1h"
SYMBOL = "EURUSD"

df = pl.from_arrow(
    DeltaTable(PATH).to_pyarrow_table(filters=[("symbol", "=", SYMBOL)])
).sort("timestamp")

print(df.head())
print(df.tail())
print(f"\nRows: {len(df):,}")
print(f"Schema: {df.schema}")