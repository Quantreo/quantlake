"""End of video 3.3 — gold resample + features end-to-end demo.

Builds a synthetic 1-minute silver DataFrame (no network needed),
resamples to 5-minute, and runs an Oryon pipeline with SMA20 + EMA20.

Notice the first 19 bars have NaN on close_sma_20 — that's the warm-up
period of the SMA window. Live runners prime the pipeline with the last
N stored bars before going live so the first live bar isn't NaN. We see
that mechanism in Module 4.
"""
from datetime import datetime, timezone

import polars as pl
from oryon import FeaturePipeline
from oryon.features import Ema, Sma

from quantlake.gold.ohlcv import resample, compute_features

# ─── Build a minimal 1m silver DataFrame ─────────────────────────────────────

n = 60  # 60 1-minute bars → 12 5-minute bars
timestamps = [datetime(2025, 4, 1, 0, i, tzinfo=timezone.utc) for i in range(n)]

silver_df = pl.DataFrame({
    "timestamp": pl.Series(timestamps, dtype=pl.Datetime("us", "UTC")),
    "symbol":    pl.Series(["BTCUSDT"] * n, dtype=pl.Utf8),
    "open":      pl.Series([100.0 + i * 0.1 for i in range(n)], dtype=pl.Float64),
    "high":      pl.Series([101.0 + i * 0.1 for i in range(n)], dtype=pl.Float64),
    "low":       pl.Series([ 99.0 + i * 0.1 for i in range(n)], dtype=pl.Float64),
    "close":     pl.Series([100.5 + i * 0.1 for i in range(n)], dtype=pl.Float64),
    "volume":    pl.Series([  1.0] * n, dtype=pl.Float64),
    "year":      pl.Series([2025] * n, dtype=pl.Int32),
    "month":     pl.Series([   4] * n, dtype=pl.Int8),
})


print(silver_df)


# ─── Resample to 5m ──────────────────────────────────────────────────────────
df_5m = resample(silver_df, "5m")
print(df_5m)


# ─── Compute features ────────────────────────────────────────────────────────
pipeline = FeaturePipeline(
    features=[
        Sma(["close"], window=5, outputs=["close_sma_5"]),
        Ema(["close"], window=5, outputs=["close_ema_5"])
    ],
    input_columns=["close"]
)

df_features = compute_features(df_5m, pipeline)

print("\n=== 5m + features ===")
print(df_features)
print(f"\nWarm-up period : {pipeline.warm_up_period()} bars")
print(f"Output columns : {pipeline.output_names()}")