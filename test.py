import polars as pl
from deltalake import DeltaTable

# Change le path vers ce que tu veux lire
PATH = "data/bronze/binance_spot_ohlcv"

df = pl.from_arrow(DeltaTable(PATH).to_pyarrow_table())

print(df.head())
print(df.tail())
print(f"\nRows: {len(df):,}")
print(f"Schema: {df.schema}")