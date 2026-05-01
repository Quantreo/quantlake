"""End of video 3.1 — silver OHLCV cleaning.

The mantra: NaN, never drop. Invalid values get marked as NaN; rows are
never deleted. This keeps the time index intact — your rolling windows
and joins don't silently skip missing bars, they see NaN and decide what
to do.

Four rules, applied in this order:
  1. inf / -inf  →  NaN  on Float64 columns
  2. null        →  NaN  on Float64 columns
  3. high < low or low < 0  →  NaN on all 4 price columns
  4. volume < 0  →  NaN on volume

Order matters — inf before null catches +inf properly, validation after
fill_null catches both nulls and infs already converted to NaN.
"""
import polars as pl

_PRICE_COLS = ("open", "high", "low", "close")


def clean_ohlcv(df: pl.DataFrame) -> pl.DataFrame:
    """Clean a 1m OHLCV DataFrame in-place (no row drops).

    Returns the same schema; NaN signals an invalid value to downstream layers.
    """
    if df.is_empty():
        return df

    # Discover Float64 columns at runtime — schema-flexible. Works on any
    # OHLCV DataFrame, with extras like spread_open or quote_volume.
    float_cols = [col for col, dtype in zip(df.columns, df.dtypes) if dtype == pl.Float64]

    # Rule 1: inf / -inf → NaN
    df = df.with_columns([
        pl.when(pl.col(c).is_infinite()).then(float("nan")).otherwise(pl.col(c)).alias(c)
        for c in float_cols
    ])

    # Rule 2: null → NaN
    df = df.with_columns([
        pl.col(c).fill_null(float("nan"))
        for c in float_cols
    ])

    # Rule 3: invalid bar (high < low or low < 0) → NaN on all 4 price columns
    if "high" in df.columns and "low" in df.columns:
        invalid_bar = (pl.col("high") < pl.col("low")) | (pl.col("low") < 0)
        price_cols = [c for c in _PRICE_COLS if c in df.columns]
        df = df.with_columns([
            pl.when(invalid_bar).then(float("nan")).otherwise(pl.col(c)).alias(c)
            for c in price_cols
        ])

    # Rule 4: negative volume → NaN volume
    if "volume" in df.columns:
        df = df.with_columns(
            pl.when(pl.col("volume") < 0).then(float("nan")).otherwise(pl.col("volume")).alias("volume")
        )

    return df