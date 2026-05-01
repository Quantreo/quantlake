"""End of video 3.2 — gold batch ingestion (resample only, no features yet).

Three public functions:

  ingest()                     resample → drop incomplete tail → save
  save()                       wraps storage.upsert with update_matched=True
  _drop_incomplete_tail()      drops the currently-forming TF bar

Why drop the incomplete tail: if we resample at 09:07 with timeframe=5m,
the 09:05 bar is incomplete (only 3 minutes of data). Writing it now
would force update_matched to overwrite later — cleaner to just skip
until 09:10 when the bar is complete.

Module 4's live runner has a poll-driven and stream-driven version of
this; for batch (historical), this is enough.

Features (compute_features) are added in v3.3.
"""
from datetime import datetime, timedelta, timezone

import polars as pl

from quantlake.config import GOLD_ROOT
from quantlake.gold.ohlcv import resample
from quantlake.helper import TF_SECONDS
from quantlake.storage import upsert


def ingest(df: pl.DataFrame, table_name: str, timeframe: str) -> pl.DataFrame:
    """Resample silver to timeframe, drop the incomplete tail, persist."""
    if df.is_empty():
        return df

    df = resample(df, timeframe)
    df = _drop_incomplete_tail(df, timeframe)
    if df.is_empty():
        return df

    tf_sec = TF_SECONDS[timeframe]
    now = datetime.now(timezone.utc)
    df = df.with_columns(
        (pl.col("timestamp") + pl.duration(seconds=tf_sec)).alias("timestamp_close"),
        pl.lit(now).cast(pl.Datetime("us", "UTC")).alias("ingested_at"),
    )
    save(df, table_name, timeframe)
    return df


def save(df: pl.DataFrame, table_name: str, timeframe: str) -> None:
    """Upsert a pre-built gold df into its Delta table.

    Uses update_matched=True so a live runner can overwrite a partial
    batch-written bar with its complete version later.
    """
    upsert(df, str(GOLD_ROOT / table_name / timeframe), update_matched=True)


def _drop_incomplete_tail(df: pl.DataFrame, timeframe: str) -> pl.DataFrame:
    """Filter out the bar currently being formed (it would be partial)."""
    tf_sec = TF_SECONDS.get(timeframe)
    if not tf_sec:
        return df
    now = datetime.now(timezone.utc)
    last_complete_open = datetime.fromtimestamp(
        int(now.timestamp()) // tf_sec * tf_sec - tf_sec, tz=timezone.utc
    )
    return df.filter(pl.col("timestamp") <= pl.lit(last_complete_open))
