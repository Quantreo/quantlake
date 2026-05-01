"""End of video 3.1 — silver ingestion orchestration.

Same shape as bronze.ingest but writes to data/silver/ and runs
clean_ohlcv on the way in. Two functions:

  ingest()   clean_ohlcv → save (the convenient one-call entry point)
  save()     wraps storage.upsert with the silver root

Same upsert as bronze (no update_matched). Silver is insert-only by
design — once a bar is cleaned and stored, it doesn't change.
"""
import polars as pl

from quantlake.config import SILVER_ROOT
from quantlake.silver.ohlcv import clean_ohlcv
from quantlake.storage import upsert


def ingest(df: pl.DataFrame, table_name: str) -> pl.DataFrame:
    """Clean OHLCV bars and persist them to the silver Delta table.

    Expects df to already carry symbol/year/month partition columns
    (added by bronze.ingest). Re-ingesting the same range is safe: merges
    on (symbol, timestamp) so no duplicates are created.

    Returns the cleaned DataFrame.
    """
    if df.is_empty():
        return df

    df = clean_ohlcv(df)
    save(df, table_name)
    return df


def save(df: pl.DataFrame, table_name: str) -> None:
    """Persist an already-cleaned DataFrame (with partition columns) to the silver Delta table."""
    if df.is_empty():
        return
    upsert(df, str(SILVER_ROOT / table_name))
