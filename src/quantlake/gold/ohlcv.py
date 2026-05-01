"""End of video 3.2 — gold OHLCV resampling.

Resamples 1m bars to a higher timeframe using Polars' group_by_dynamic.

The mantra: closed='left', label='left'. The 09:00 bar contains the
1-minute bars from 09:00:00 to 09:04:59. The 09:05 1-minute bar starts
the next 5-minute bar. If you mix this up, your backtest is shifted by
one timeframe and your trades fire one bar too late.

compute_features comes in v3.3 — for now this module is resample-only.
"""
import polars as pl
from oryon import FeaturePipeline

_OHLC = ("open", "high", "low", "close")


def resample(df: pl.DataFrame, timeframe: str) -> pl.DataFrame:
    """Resample 1m OHLC(V) bars to a higher timeframe.

    Expects df to carry a 'symbol' column (added by bronze.ingest).
    ``volume`` is aggregated when present, skipped otherwise (some
    composite silvers intentionally drop it).

    Returns a new DataFrame with the same schema plus recomputed year/month.
    """
    if df.is_empty():
        return df

    has_volume = "volume" in df.columns
    cols = ["timestamp", "symbol", *_OHLC] + (["volume"] if has_volume else [])

    agg_exprs = [
        pl.col("open").first(),
        pl.col("high").max(),
        pl.col("low").min(),
        pl.col("close").last(),
    ]
    if has_volume:
        agg_exprs.append(pl.col("volume").sum())

    resampled = (
        df.select(cols)
        .sort("timestamp")
        .group_by_dynamic(
            "timestamp",
            every=timeframe,
            closed="left",
            label="left",
            group_by="symbol",
        )
        .agg(*agg_exprs)
    )

    return resampled.with_columns(
        pl.col("timestamp").dt.year().cast(pl.Int32).alias("year"),
        pl.col("timestamp").dt.month().cast(pl.Int8).alias("month"),
    ).sort("timestamp")


def compute_features(df: pl.DataFrame, pipeline: FeaturePipeline) -> pl.DataFrame:
    """Run an Oryon FeaturePipeline on df and append the feature columns.

    Processes each symbol independently so state does not bleed across instruments.
    Warm-up bars produce NaN — rows are never dropped.
    """
    if df.is_empty():
        return df

    input_cols = pipeline.input_names()
    output_cols = pipeline.output_names()

    parts = []
    for symbol in df["symbol"].unique(maintain_order=False).to_list():
        symbol_df = df.filter(pl.col("symbol") == symbol).sort("timestamp")
        data = symbol_df.select(input_cols).to_numpy().tolist()
        # run_research = batch mode of Oryon. Same numerical output as
        # update() called bar-by-bar (we use update() in live runners).
        # State is reset between symbol iterations because each iteration
        # drives a different pipeline instance? No — same instance, but
        # run_research resets state automatically on each call.
        raw = pipeline.run_research(data)
        feature_df = pl.DataFrame(
            {name: [row[i] for row in raw] for i, name in enumerate(output_cols)},
            schema={name: pl.Float64 for name in output_cols},
        )
        parts.append(pl.concat([symbol_df, feature_df], how="horizontal"))

    return pl.concat(parts, how="vertical").sort("timestamp")