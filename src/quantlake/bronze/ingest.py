from datetime import datetime, timezone
import polars as pl
from quantlake.bronze.base import HistoricalConnector
from quantlake.config import BRONZE_ROOT
from quantlake.storage import upsert


def ingest(connector: HistoricalConnector, symbol, start, end):
    df = connector.fetch(symbol=symbol, start=start, end=end)
    if df.is_empty():
        return df
    df = add_partition_columns(df, symbol)
    save(df, connector.TABLE_NAME)
    return df


def save(df, table_name):
    upsert(df, str(BRONZE_ROOT / table_name))


def add_partition_columns(df, symbol):
    df = df.with_columns(
        pl.lit(symbol).alias("symbol"),
        pl.col("timestamp").dt.year().cast(pl.Int32).alias("year"),
        pl.col("timestamp").dt.month().cast(pl.Int8).alias("month"),
    )
    if "ingested_at" not in df.columns:
        df = df.with_columns(
            pl.lit(datetime.now(timezone.utc)).cast(pl.Datetime("us", "UTC")).alias("ingested_at")
        )
    return df