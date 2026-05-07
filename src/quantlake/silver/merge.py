"""End of v0.5.4 - Composite silver tables for multi-source feeds.

One silver in this module aggregates a historical source with a live
source covering the same concept:

  macro_ohlcv : dukascopy (spot, historical) + capital.com (CFD, live)
                - FX, commodity, index 1m OHLCV

Each bronze source's ingestion path calls save_macro below after cleaning.
Delta's (symbol, timestamp) merge dedupes if the two sources ever overlap,
so historical and live can be re-run safely.

Only the canonical columns are written - source-specific auxiliary columns
(dukascopy spreads, capital spread_open/close) are dropped so the
composite silver keeps a stable schema.
"""
import polars as pl

import quantlake.silver.ingest as silver

MACRO_OHLCV = "macro_ohlcv"
ETH_GAS = "eth_gas"

# Volume is deliberately absent: Dukascopy's FX volume is interbank-aggregated
# (partially tick-count for indices/commodities) while Capital.com's is CFD
# client flow - incompatible units. Leaving both would create a spurious jump
# at the Duka -> Capital boundary. Strategies that need volume should read the
# relevant bronze table directly (single source -> unambiguous semantics).
_MACRO_SCHEMA = {
    "timestamp":   pl.Datetime("us", "UTC"),
    "symbol":      pl.Utf8,
    "open":        pl.Float64,
    "high":        pl.Float64,
    "low":         pl.Float64,
    "close":       pl.Float64,
    "ingested_at": pl.Datetime("us", "UTC"),
    "year":        pl.Int32,
    "month":       pl.Int32,
}


_ETH_GAS_SCHEMA = {
    "timestamp":   pl.Datetime("us", "UTC"),
    "symbol":      pl.Utf8,
    "open":        pl.Float64,
    "high":        pl.Float64,
    "low":         pl.Float64,
    "close":       pl.Float64,
    "avg_gas":     pl.Float64,
    "avg_time":    pl.Float64,
    "avg_tx":      pl.Float64,
    "ingested_at": pl.Datetime("us", "UTC"),
    "year":        pl.Int32,
    "month":       pl.Int32,
}


def save_macro(df: pl.DataFrame) -> None:
    """Project to the macro silver schema and upsert into silver/macro_ohlcv.

    Used by both Dukascopy (spot historical) and Capital.com (CFD live)
    ingestion paths. Callers are responsible for applying any price-scale
    adjustment (see applications/historical/macro_silver.py).
    """
    if df.is_empty():
        return
    silver.ingest(_project(df, _MACRO_SCHEMA), MACRO_OHLCV)


def save_eth_gas(df: pl.DataFrame) -> None:
    """Project to eth_gas silver schema and upsert.

    Tolerates sources that don't provide every column (e.g. Dune has
    no avg_gas/avg_time/avg_tx). Missing columns are filled with typed
    nulls so DeltaLake accepts them.
    """
    if df.is_empty():
        return
    silver.ingest(_project(df, _ETH_GAS_SCHEMA), ETH_GAS)


def _project(df: pl.DataFrame, schema: dict[str, pl.DataType]) -> pl.DataFrame:
    """Project df onto schema. Existing columns are cast, missing ones
    are filled with typed nulls (Delta refuses Null dtype, so the type
    has to be explicit).
    """
    present = set(df.columns)
    return df.select([
        pl.col(c).cast(t) if c in present else pl.lit(None, dtype=t).alias(c)
        for c, t in schema.items()
    ])









