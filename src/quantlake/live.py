"""Live WebSocket runner — bronze → silver → gold with features.

Entry point: ``run(ws_connector, rest_connector, symbols, gold_table, ...)``.

Design split in two paths so per-bar latency stays bounded by compute only:

  HOT PATH  (every incoming 1m bar, zero I/O)
    bar → bronze.add_partition_columns → clean_ohlcv
        → append to in-memory buffers
        → if the bar closes a gold TF window:
              resample → transform_gold → pipeline.update → emit + queue

  COLD PATH (background task every FLUSH_INTERVAL seconds)
    snapshot buffers → Delta writes for bronze, silver, gold

Startup sequence (in order):
  1. Warmup each symbol's pipeline from stored gold history.
  2. Reconstitute the in-memory gold buffer from silver for the current
     incomplete TF window (crash recovery — otherwise the first gold bar
     after restart would be built from partial data).
  3. Fetch any bars missed since the last silver save via REST (gap fill).
  4. Flush gap-fill data to Delta before going live.
  5. Enter the WebSocket stream; transform each bar, gap-fill mid-stream
     on disconnect.

Strategies can inject a ``transform_gold`` callback to join slow-moving
data (e.g. silver/eth_gas) into the resampled bar before features are
computed.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Callable

import polars as pl
from deltalake import DeltaTable
from oryon import FeaturePipeline

import quantlake.bronze.ingest as bronze
import quantlake.gold.ingest as gold
import quantlake.silver.ingest as silver
from quantlake.bronze.base import HistoricalConnector, StreamConnector
from quantlake.config import GOLD_ROOT, SILVER_ROOT
from quantlake.gold.ohlcv import resample
from quantlake.helper import TF_SECONDS
from quantlake.silver.ohlcv import clean_ohlcv

FLUSH_INTERVAL = 60  # seconds between background Delta flushes

_BUFFER_COLS = ["timestamp", "timestamp_close", "open", "high", "low", "close", "volume", "symbol"]

TransformGold = Callable[[pl.DataFrame, str], pl.DataFrame]


# ── Startup helpers ────────────────────────────────────────────────────────

def _last_silver_ts(source_table: str, symbol: str) -> datetime | None:
    path = str(SILVER_ROOT / source_table)
    if not DeltaTable.is_deltatable(path):
        return None
    df = pl.from_arrow(
        DeltaTable(path).to_pyarrow_table(filters=[("symbol", "=", symbol)], columns=["timestamp"])
    )
    return df["timestamp"].max() if not df.is_empty() else None


def _current_tf_start(ts: datetime, timeframe: str) -> datetime:
    tf_sec = TF_SECONDS[timeframe]
    aligned = int(ts.timestamp()) // tf_sec * tf_sec
    return datetime.fromtimestamp(aligned, tz=timezone.utc)


def _reconstitute_buffer(
    symbol: str,
    source_table: str,
    timeframe: str,
    last: datetime,
    gold_buffers: dict[str, list[pl.DataFrame]],
) -> None:
    """Reload silver bars of the current incomplete TF window into the gold buffer.

    Without this, on restart mid-window the first gold bar would only aggregate
    bars that arrived after restart — silently producing a broken bar that
    Oryon would then consume.
    """
    tf_start = _current_tf_start(last + timedelta(minutes=1), timeframe)
    if tf_start > last:
        return
    path = str(SILVER_ROOT / source_table)
    if not DeltaTable.is_deltatable(path):
        return
    df = (
        pl.from_arrow(DeltaTable(path).to_pyarrow_table(filters=[("symbol", "=", symbol)]))
        .filter((pl.col("timestamp") >= tf_start) & (pl.col("timestamp") <= last))
        .sort("timestamp")
    )
    if not df.is_empty():
        gold_buffers[symbol].append(df.select(_BUFFER_COLS))


def _warmup_pipeline(pipeline: FeaturePipeline, gold_table: str, timeframe: str, symbol: str) -> None:
    """Seed Oryon state with the last warm_up_period gold bars."""
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


# ── Hot path ───────────────────────────────────────────────────────────────

def _closes_gold_bar(ts: datetime, timeframe: str) -> bool:
    tf_sec = TF_SECONDS[timeframe]
    return int(ts.timestamp()) // tf_sec != int((ts + timedelta(minutes=1)).timestamp()) // tf_sec


def _bar_to_df(bar: dict) -> pl.DataFrame:
    return pl.DataFrame({
        "timestamp":       pl.Series([bar["timestamp"]],       dtype=pl.Datetime("us", "UTC")),
        "timestamp_close": pl.Series([bar["timestamp_close"]], dtype=pl.Datetime("us", "UTC")),
        "open":            pl.Series([bar["open"]],            dtype=pl.Float64),
        "high":            pl.Series([bar["high"]],            dtype=pl.Float64),
        "low":             pl.Series([bar["low"]],             dtype=pl.Float64),
        "close":           pl.Series([bar["close"]],           dtype=pl.Float64),
        "volume":          pl.Series([bar["volume"]],          dtype=pl.Float64),
        "ingested_at":     pl.Series([bar["ingested_at"]],     dtype=pl.Datetime("us", "UTC")),
    })


def _process_df(
    df: pl.DataFrame,
    symbol: str,
    timeframe: str,
    bronze_buffers: dict[str, list[pl.DataFrame]],
    silver_buffers: dict[str, list[pl.DataFrame]],
    gold_buffers:   dict[str, list[pl.DataFrame]],
    gold_output:    dict[str, list[pl.DataFrame]],
    pipelines:      dict[str, FeaturePipeline] | None,
    transform_gold: TransformGold | None,
    from_live:      bool,
) -> None:
    """Push one or more bars through bronze → silver → (maybe) gold. Zero I/O.

    ``from_live=False`` for catch-up paths (startup gap-fill, reconnect
    gap-fill) so the resulting gold bars are flagged as historical.
    """
    bronze_df = bronze.add_partition_columns(df, symbol)
    bronze_buffers[symbol].append(bronze_df)

    silver_df = clean_ohlcv(bronze_df)
    silver_buffers[symbol].append(silver_df)

    window_schema = silver_df.select(_BUFFER_COLS).schema
    for row in silver_df.select(_BUFFER_COLS).iter_rows(named=True):
        gold_buffers[symbol].append(pl.DataFrame([row], schema=window_schema))
        if _closes_gold_bar(row["timestamp"], timeframe):
            _emit_gold_bar(symbol, timeframe, gold_buffers, gold_output, pipelines, transform_gold, from_live)


def _emit_gold_bar(
    symbol: str,
    timeframe: str,
    gold_buffers:   dict[str, list[pl.DataFrame]],
    gold_output:    dict[str, list[pl.DataFrame]],
    pipelines:      dict[str, FeaturePipeline] | None,
    transform_gold: TransformGold | None,
    from_live:      bool,
) -> None:
    """Resample the buffered silver window, run features, queue for flush."""
    buf = pl.concat(gold_buffers[symbol])
    timestamp_close = buf["timestamp_close"].max()

    gold_bar = resample(buf, timeframe)

    if transform_gold is not None:
        gold_bar = transform_gold(gold_bar, symbol)

    if pipelines and symbol in pipelines:
        pipeline = pipelines[symbol]
        inputs = list(gold_bar.select(pipeline.input_names()).row(0))
        outputs = pipeline.update(inputs)
        feats = pl.DataFrame(
            {name: [outputs[i]] for i, name in enumerate(pipeline.output_names())},
            schema={name: pl.Float64 for name in pipeline.output_names()},
        )
        gold_bar = pl.concat([gold_bar, feats], how="horizontal")

    now = datetime.now(timezone.utc)
    latency_ms = int((now - timestamp_close).total_seconds() * 1000)
    gold_bar = gold_bar.with_columns(
        pl.lit(timestamp_close).cast(pl.Datetime("us", "UTC")).alias("timestamp_close"),
        pl.lit(now).cast(pl.Datetime("us", "UTC")).alias("ingested_at"),
        pl.lit(latency_ms).alias("latency_ms"),
        pl.lit(from_live).alias("live"),
    )

    print(gold_bar)
    gold_output[symbol].append(gold_bar)
    gold_buffers[symbol] = []


# ── Cold path ──────────────────────────────────────────────────────────────

def _flush_snapshot(
    bronze_snap: dict[str, pl.DataFrame],
    silver_snap: dict[str, pl.DataFrame],
    gold_snap:   dict[str, pl.DataFrame],
    source_table: str,
    gold_table: str,
    timeframe: str,
) -> None:
    for df in bronze_snap.values():
        bronze.save(df, source_table)
    for df in silver_snap.values():
        silver.save(df, source_table)
    for df in gold_snap.values():
        gold.save(df, gold_table, timeframe)


def _drain_buffers(
    bronze_buffers: dict[str, list[pl.DataFrame]],
    silver_buffers: dict[str, list[pl.DataFrame]],
    gold_output:    dict[str, list[pl.DataFrame]],
) -> tuple[dict[str, pl.DataFrame], dict[str, pl.DataFrame], dict[str, pl.DataFrame]]:
    """Snapshot non-empty buffers and clear the originals."""
    bronze_snap = {s: pl.concat(f) for s, f in bronze_buffers.items() if f}
    silver_snap = {s: pl.concat(f) for s, f in silver_buffers.items() if f}
    gold_snap   = {s: pl.concat(f) for s, f in gold_output.items()   if f}
    for s in bronze_snap: bronze_buffers[s].clear()
    for s in silver_snap: silver_buffers[s].clear()
    for s in gold_snap:   gold_output[s].clear()
    return bronze_snap, silver_snap, gold_snap


async def _flush_loop(
    bronze_buffers: dict[str, list[pl.DataFrame]],
    silver_buffers: dict[str, list[pl.DataFrame]],
    gold_output:    dict[str, list[pl.DataFrame]],
    source_table: str,
    gold_table: str,
    timeframe: str,
) -> None:
    while True:
        await asyncio.sleep(FLUSH_INTERVAL)
        bronze_snap, silver_snap, gold_snap = _drain_buffers(
            bronze_buffers, silver_buffers, gold_output
        )
        if bronze_snap or silver_snap or gold_snap:
            await asyncio.to_thread(
                _flush_snapshot, bronze_snap, silver_snap, gold_snap,
                source_table, gold_table, timeframe,
            )


def _sync_flush(
    bronze_buffers: dict[str, list[pl.DataFrame]],
    silver_buffers: dict[str, list[pl.DataFrame]],
    gold_output:    dict[str, list[pl.DataFrame]],
    source_table: str,
    gold_table: str,
    timeframe: str,
) -> None:
    """Synchronous flush — used at startup (after gap fill) and on shutdown."""
    bronze_snap, silver_snap, gold_snap = _drain_buffers(
        bronze_buffers, silver_buffers, gold_output
    )
    if bronze_snap or silver_snap or gold_snap:
        _flush_snapshot(bronze_snap, silver_snap, gold_snap, source_table, gold_table, timeframe)


# ── Entry point ────────────────────────────────────────────────────────────

async def run(
    ws_connector:   StreamConnector,
    rest_connector: HistoricalConnector,
    symbols:        list[str],
    gold_table:     str,
    timeframe:      str = "5m",
    pipelines:      dict[str, FeaturePipeline] | None = None,
    transform_gold: TransformGold | None = None,
) -> None:
    """Run the live WS pipeline for an application.

    Args:
        ws_connector:   WebSocket connector for the primary source. Bronze +
                        silver are written under ``ws_connector.TABLE_NAME``.
        rest_connector: REST connector from the same source family — used
                        for gap fill at startup and on stream disconnects.
        symbols:        symbols to subscribe to.
        gold_table:     destination gold table (= strategy name).
        timeframe:      gold timeframe: "5m", "1h", "1d", etc.
        pipelines:      one Oryon FeaturePipeline per symbol (no sharing of
                        indicator state across symbols). None skips features.
        transform_gold: (gold_bar_df, symbol) -> gold_bar_df. Called after
                        resample, before features. Use for as-of joins onto
                        slow-moving silvers (e.g. silver/eth_gas).
    """
    source_table = ws_connector.TABLE_NAME

    bronze_buffers: dict[str, list[pl.DataFrame]] = {s: [] for s in symbols}
    silver_buffers: dict[str, list[pl.DataFrame]] = {s: [] for s in symbols}
    gold_buffers:   dict[str, list[pl.DataFrame]] = {s: [] for s in symbols}
    gold_output:    dict[str, list[pl.DataFrame]] = {s: [] for s in symbols}
    last_ts: dict[str, datetime | None] = {}

    # 1. Pipeline warmup
    if pipelines:
        for symbol, pipeline in pipelines.items():
            _warmup_pipeline(pipeline, gold_table, timeframe, symbol)

    # 2 + 3. Buffer reconstitution + gap fill
    for symbol in symbols:
        last = _last_silver_ts(source_table, symbol)
        last_ts[symbol] = last
        if last is None:
            continue

        _reconstitute_buffer(symbol, source_table, timeframe, last, gold_buffers)

        gap_start = last + timedelta(minutes=1)
        now = datetime.now(timezone.utc)
        if gap_start < now:
            gap_df = rest_connector.fetch(symbol, gap_start, now)
            if not gap_df.is_empty():
                _process_df(
                    gap_df, symbol, timeframe,
                    bronze_buffers, silver_buffers, gold_buffers, gold_output,
                    pipelines, transform_gold, from_live=False,
                )
                last_ts[symbol] = gap_df["timestamp"].max()

    # 4. Flush gap-fill data before going live
    _sync_flush(bronze_buffers, silver_buffers, gold_output, source_table, gold_table, timeframe)

    flush_task = asyncio.create_task(
        _flush_loop(bronze_buffers, silver_buffers, gold_output, source_table, gold_table, timeframe)
    )

    # 5. Live stream
    try:
        async for bar in ws_connector.stream(symbols):
            symbol = bar["symbol"]
            ts = bar["timestamp"]

            prev = last_ts.get(symbol)
            if prev is not None and ts - prev > timedelta(minutes=1):
                gap_df = rest_connector.fetch(symbol, prev + timedelta(minutes=1), ts)
                if not gap_df.is_empty():
                    _process_df(
                        gap_df, symbol, timeframe,
                        bronze_buffers, silver_buffers, gold_buffers, gold_output,
                        pipelines, transform_gold, from_live=False,
                    )

            _process_df(
                _bar_to_df(bar), symbol, timeframe,
                bronze_buffers, silver_buffers, gold_buffers, gold_output,
                pipelines, transform_gold, from_live=True,
            )
            last_ts[symbol] = ts
    finally:
        flush_task.cancel()
        _sync_flush(bronze_buffers, silver_buffers, gold_output, source_table, gold_table, timeframe)
