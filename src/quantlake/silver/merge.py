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

# Volume is deliberately absent: Dukascopy's FX volume is interbank-aggregated
# (partially tick-count for indices/commodities) while Capital.com's is CFD
# client flow - incompatible units. Leaving both would create a spurious jump
# at the Duka -> Capital boundary. Strategies that need volume should read the
# relevant bronze table directly (single source -> unambiguous semantics).
_MACRO_COLS = [
    "timestamp", "symbol", "open", "high", "low", "close",
    "ingested_at", "year", "month",
]


def save_macro(df: pl.DataFrame) -> None:
    """Project to the macro silver schema and upsert into silver/macro_ohlcv.

    Used by both Dukascopy (spot historical) and Capital.com (CFD live)
    ingestion paths. Callers are responsible for applying any price-scale
    adjustment (see applications/historical/macro_silver.py).
    """
    if df.is_empty():
        return
    silver.ingest(_project(df, _MACRO_COLS), MACRO_OHLCV)


def _project(df: pl.DataFrame, cols: list[str]) -> pl.DataFrame:
    """Keep only `cols`, filling any missing with null (-> NaN after clean)."""
    present = set(df.columns)
    return df.select([
        pl.col(c) if c in present else pl.lit(None).alias(c)
        for c in cols
    ])









