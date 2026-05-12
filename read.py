import polars as pl
from deltalake import DeltaTable

PATH = "data/gold/wheat_stress/1d"

df = pl.from_arrow(
    DeltaTable(PATH).to_pyarrow_table())

print(df.head())
print(df.tail())
print(f"\nRows: {len(df):,}")
print(f"Schema: {df.schema}")