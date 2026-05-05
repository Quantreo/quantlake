"""Demo - how the macro offset is computed, step by step.

Three steps :
    1. Load both bronzes for one symbol (here EURUSD).
    2. Inner-join on timestamp to keep only the OVERLAP minutes.
    3. Compute (capital_close - dukascopy_close) and take the median.

Also shows why we use the median rather than the mean : CFD data has
occasional huge outliers (news, rollovers, illiquid minutes), and the
median ignores them.

Run AFTER:
    poetry run python applications/historical/capital.py
    poetry run python applications/historical/dukascopy.py

Then:
    poetry run python examples/silver/offset_example.py
"""
import polars as pl
from deltalake import DeltaTable

from quantlake.bronze.connectors.capital_rest import CapitalComOHLCVRestConnector
from quantlake.bronze.connectors.dukascopy import DukascopyOHLCVConnector
from quantlake.config import BRONZE_ROOT

SYMBOL = "EURUSD"


def load_bronze(table: str, symbol: str) -> pl.DataFrame:
    df = pl.from_arrow(
        DeltaTable(str(BRONZE_ROOT / table)).to_pyarrow_table(
            filters=[("symbol", "=", symbol)]
        )
    )
    return df.sort("timestamp")


# 1. Load both bronzes for one symbol.
capi = load_bronze(CapitalComOHLCVRestConnector.TABLE_NAME, SYMBOL)
duka = load_bronze(DukascopyOHLCVConnector.TABLE_NAME, SYMBOL)

print(f"Capital   : {len(capi):>10,} bars  from {capi['timestamp'].min()}  to {capi['timestamp'].max()}")
print(f"Dukascopy : {len(duka):>10,} bars  from {duka['timestamp'].min()}  to {duka['timestamp'].max()}")

# 2. Inner-join on timestamp -> overlap.
overlap = (
    capi.select("timestamp", pl.col("close").alias("capi"))
    .join(
        duka.select("timestamp", pl.col("close").alias("duka")),
        on="timestamp",
        how="inner",
    )
    .with_columns((pl.col("capi") - pl.col("duka")).alias("diff"))
    .sort("timestamp")
)

print(f"\nOverlap   : {len(overlap):>10,} bars where both sources have data\n")
print("First 5 rows of the overlap (capi / duka / diff):")
print(overlap.head())

# 3. Show extreme outliers, then compare mean vs median.
print("\n5 largest absolute diffs (outliers - news, rollovers, etc.):")
print(overlap.sort(pl.col("diff").abs(), descending=True).head())

mean_offset   = float(overlap["diff"].mean())
median_offset = float(overlap["diff"].median())

print(f"\nOffset (mean)   : {mean_offset:+.6f}   <- pulled by outliers")
print(f"Offset (median) : {median_offset:+.6f}   <- robust, this is the one we use")
