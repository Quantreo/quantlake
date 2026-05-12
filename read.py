import polars as pl
from deltalake import DeltaTable

PATH = "data/gold/ml_based_strategy/5m"

df = (
    pl.from_arrow(DeltaTable(PATH).to_pyarrow_table())
    .select("timestamp", "close", "ml_signal")
    .sort("timestamp")
)

print(df.tail(20))
print(f"\nRows: {len(df):,}")