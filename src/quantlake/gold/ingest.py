"""End of v0.4.0 — gold ingest extended for live runners.

Two new functions added vs v0.3.3:

  rebuild_from_silver  rebuild gold for one symbol from all silver rows
                       (used at startup of live scripts, with a fresh
                       pipeline so batch state doesn't contaminate live)
  warmup_pipeline      seed pipeline state with the last N stored gold
                       bars (so the first live bar isn't NaN)

Plus a poll-driven equivalent of live._emit_gold_bar:

  build_live_bar       read the just-closed TF window from silver, resample,
                       apply transform_gold + pipeline.update, save
                       (used by Module 6's poll-based live scripts)

The batch path (ingest, save, _drop_incomplete_tail) is unchanged from v0.3.3.
"""
from datetime import datetime, timedelta, timezone
from typing import Callable

import polars as pl
from deltalake import DeltaTable
from oryon import FeaturePipeline

from quantlake.config import GOLD_ROOT, SILVER_ROOT
from quantlake.gold.ohlcv import compute_features, resample
from quantlake.helper import TF_SECONDS
from quantlake.storage import upsert

__all__ = [
    "ingest", "save",
    "warmup_pipeline", "build_live_bar", "rebuild_from_silver",
]

TransformGold = Callable[[pl.DataFrame, str], pl.DataFrame]


# ── Batch path (historical) ────────────────────────────────────────────────

def ingest(
    df: pl.DataFrame,
    table_name: str,
    timeframe: str,
    pipeline: FeaturePipeline | None = None,
) -> pl.DataFrame:
    """Resample a silver OHLCV df, optionally compute features, persist to gold."""
    if df.is_empty():
        return df

    df = resample(df, timeframe)
    df = _drop_incomplete_tail(df, timeframe)
    if df.is_empty():
        return df

    if pipeline is not None:
        df = compute_features(df, pipeline)

    tf_sec = TF_SECONDS[timeframe]
    now = datetime.now(timezone.utc)
    df = df.with_columns(
        (pl.col("timestamp") + pl.duration(seconds=tf_sec)).alias("timestamp_close"),
        pl.lit(now).cast(pl.Datetime("us", "UTC")).alias("ingested_at"),
        pl.lit(None).cast(pl.Int64).alias("latency_ms"),
        pl.lit(False).alias("live"),
    )
    save(df, table_name, timeframe)
    return df


def save(df: pl.DataFrame, table_name: str, timeframe: str) -> None:
    """Upsert a pre-built gold df into its Delta table."""
    upsert(df, str(GOLD_ROOT / table_name / timeframe), update_matched=True)


# ── Historical rebuild (live-script startup) ───────────────────────────────

def rebuild_from_silver(
    silver_table:   str,
    symbol:         str,
    gold_table:     str,
    timeframe:      str,
    pipeline:       FeaturePipeline | None = None,
    transform_gold: "TransformGold | None" = None,
) -> pl.DataFrame | None:
    """Rebuild gold for one symbol from all silver rows on disk.

    Reads silver for ``symbol``, resamples to ``timeframe``, applies
    ``transform_gold`` (for as-of joins onto other silvers), computes
    features via ``pipeline.run_research`` (batch mode), upserts to gold.

    Idempotent — the merge on (symbol, timestamp) overwrites existing
    gold rows with freshly-computed values. Live scripts should call
    this at startup so gold is pre-populated with historical bars
    (with proper feature warm-up) before the live stream begins.

    Pass a fresh pipeline instance: after this call, the pipeline's
    state sits at end-of-history. The live runner's own warmup then
    re-seeds its own pipeline instance from the stored gold.
    """
    silver_path = str(SILVER_ROOT / silver_table)
    if not DeltaTable.is_deltatable(silver_path):
        return None

    df = (
        pl.from_arrow(
            DeltaTable(silver_path).to_pyarrow_table(filters=[("symbol", "=", symbol)])
        )
        .sort("timestamp")
    )
    if df.is_empty():
        return None

    df = resample(df, timeframe)
    df = _drop_incomplete_tail(df, timeframe)
    if df.is_empty():
        return None

    if transform_gold is not None:
        df = transform_gold(df, symbol)

    if pipeline is not None:
        df = compute_features(df, pipeline)

    tf_sec = TF_SECONDS[timeframe]
    now = datetime.now(timezone.utc)
    df = df.with_columns(
        (pl.col("timestamp") + pl.duration(seconds=tf_sec)).alias("timestamp_close"),
        pl.lit(now).cast(pl.Datetime("us", "UTC")).alias("ingested_at"),
        pl.lit(None).cast(pl.Int64).alias("latency_ms"),
        pl.lit(False).alias("live"),
    )
    save(df, gold_table, timeframe)
    return df


# ── Live path (poll-driven) ────────────────────────────────────────────────

def warmup_pipeline(
    pipeline: FeaturePipeline,
    gold_table: str,
    timeframe: str,
    symbol: str,
) -> None:
    """Seed pipeline state with the last warm_up_period stored gold bars.

    Without this, the first live ticks would return NaN for features with
    non-zero warmup (SMA/EMA windowed, etc.).
    """
    n = pipeline.warm_up_period()
    if n == 0:
        return
    path = str(GOLD_ROOT / gold_table / timeframe)
    if not DeltaTable.is_deltatable(path):
        return
    df = (
        pl.from_arrow(DeltaTable(path).to_pyarrow_table(filters=[("symbol", "=", symbol)]))
        .sort("timestamp").tail(n).select(pipeline.input_names())
    )
    if df.is_empty():
        return
    pipeline.run_research(df.to_numpy().tolist())


def build_live_bar(
    silver_table:   str,
    symbol:         str,
    gold_table:     str,
    timeframe:      str,
    pipeline:       FeaturePipeline | None = None,
    transform_gold: TransformGold | None = None,
) -> pl.DataFrame | None:
    """Build and persist the just-closed gold TF bar for ``symbol``.

    Used by Module 6's poll-driven live scripts (eth_data, wheat_stress).
    The WebSocket runner has its own emit path.
    """
    tf_sec = TF_SECONDS[timeframe]
    now = datetime.now(timezone.utc)
    bar_open  = datetime.fromtimestamp((int(now.timestamp()) // tf_sec - 1) * tf_sec, tz=timezone.utc)
    bar_close = bar_open + timedelta(seconds=tf_sec)

    if _last_gold_ts(gold_table, timeframe, symbol) is not None \
            and _last_gold_ts(gold_table, timeframe, symbol) >= bar_open:
        return None

    silver_path = str(SILVER_ROOT / silver_table)
    if not DeltaTable.is_deltatable(silver_path):
        return None

    window_1m = (
        pl.from_arrow(
            DeltaTable(silver_path).to_pyarrow_table(filters=[("symbol", "=", symbol)])
        )
        .filter((pl.col("timestamp") >= bar_open) & (pl.col("timestamp") < bar_close))
        .sort("timestamp")
    )
    if window_1m.is_empty():
        return None

    tf_df = resample(window_1m, timeframe)
    if tf_df.is_empty():
        return None

    if transform_gold is not None:
        tf_df = transform_gold(tf_df, symbol)

    if pipeline is not None:
        inputs = list(tf_df.select(pipeline.input_names()).row(0))
        outputs = pipeline.update(inputs)
        feats = pl.DataFrame(
            {name: [outputs[i]] for i, name in enumerate(pipeline.output_names())},
            schema={name: pl.Float64 for name in pipeline.output_names()},
        )
        tf_df = pl.concat([tf_df, feats], how="horizontal")

    now_ts = datetime.now(timezone.utc)
    tf_df = tf_df.with_columns(
        (pl.col("timestamp") + pl.duration(seconds=tf_sec)).alias("timestamp_close"),
        pl.lit(now_ts).cast(pl.Datetime("us", "UTC")).alias("ingested_at"),
        pl.lit(True).alias("live"),
    ).with_columns(
        ((pl.lit(now_ts).cast(pl.Datetime("us", "UTC")) - pl.col("timestamp_close"))
         .dt.total_seconds() * 1000).cast(pl.Int64).alias("latency_ms"),
    )

    save(tf_df, gold_table, timeframe)
    return tf_df


# ── Helpers ────────────────────────────────────────────────────────────────

def _drop_incomplete_tail(df: pl.DataFrame, timeframe: str) -> pl.DataFrame:
    tf_sec = TF_SECONDS.get(timeframe)
    if not tf_sec:
        return df
    now = datetime.now(timezone.utc)
    last_complete_open = datetime.fromtimestamp(
        int(now.timestamp()) // tf_sec * tf_sec - tf_sec, tz=timezone.utc
    )
    return df.filter(pl.col("timestamp") <= pl.lit(last_complete_open))


def _last_gold_ts(gold_table: str, timeframe: str, symbol: str) -> datetime | None:
    path = str(GOLD_ROOT / gold_table / timeframe)
    if not DeltaTable.is_deltatable(path):
        return None
    df = pl.from_arrow(
        DeltaTable(path).to_pyarrow_table(filters=[("symbol", "=", symbol)], columns=["timestamp"])
    )
    return df["timestamp"].max() if not df.is_empty() else None
