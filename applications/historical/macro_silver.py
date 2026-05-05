"""End of v0.5.4 - Build silver/macro_ohlcv from bronze/dukascopy_ohlcv
+ bronze/capitalcom_ohlcv.

Covers macro instruments - FX (EURUSD, GBPUSD), metals (XAUUSD), indices
(SPX500), commodities (WTI). Dukascopy is the deep historical source
(near-spot); Capital.com is the live CFD feed.

Run AFTER the two bronze ingesters:

    historical/dukascopy.py    -> bronze/dukascopy_ohlcv
    historical/capital.py      -> bronze/capitalcom_ohlcv
    historical/macro_silver.py -> silver/macro_ohlcv (this script)

Per instrument:
  1. Compute offset = median(capital_close - dukascopy_close) on the 1m
     overlap. A scalar, in price units.
  2. Write capital bars to silver/macro_ohlcv on their **native** scale -
     Capital is the live source, so backtests over the recent tail run
     on unmodified prices.
  3. Write dukascopy bars to silver/macro_ohlcv with prices **shifted by
     +offset** so the deep historical tail sits on Capital's scale and
     the timeline is continuous at the source boundary.

Offsets are persisted to data/macro_offsets.json for transparency.
The live script (applications/live/fx.py from v0.5.3, or any future
macro live script) doesn't need them - Capital writes on its native
scale during live ticks, matching the silver.

Safe to re-run: Delta merge dedupes on (symbol, timestamp).

Usage:
    poetry run python applications/historical/macro_silver.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import polars as pl
from deltalake import DeltaTable

from quantlake.bronze.connectors.capital_rest import CapitalComOHLCVRestConnector
from quantlake.bronze.connectors.dukascopy import DukascopyOHLCVConnector
from quantlake.config import BRONZE_ROOT, DATA_ROOT
from quantlake.silver import merge
from quantlake.silver.ohlcv import clean_ohlcv
from symbols import MACRO_INSTRUMENTS, MacroInstrument

_PRICE_COLS = ("open", "high", "low", "close")
OFFSETS_FILE = DATA_ROOT / "macro_offsets.json"


def _load_bronze(table: str, symbol: str) -> pl.DataFrame | None:
    path = str(BRONZE_ROOT / table)
    if not DeltaTable.is_deltatable(path):
        return None
    df = pl.from_arrow(
        DeltaTable(path).to_pyarrow_table(filters=[("symbol", "=", symbol)])
    )
    return df if not df.is_empty() else None


def _compute_offset(capi: pl.DataFrame, duka: pl.DataFrame) -> float:
    overlap = (
        capi.select("timestamp", pl.col("close").alias("capi_close"))
        .join(
            duka.select("timestamp", pl.col("close").alias("duka_close")),
            on="timestamp",
            how="inner",
        )
    )
    if overlap.is_empty():
        return 0.0
    return float((overlap["capi_close"] - overlap["duka_close"]).median())


def _shift_prices(df: pl.DataFrame, offset: float) -> pl.DataFrame:
    return df.with_columns(
        [(pl.col(c) + offset).alias(c) for c in _PRICE_COLS if c in df.columns]
    )


def _build(inst: MacroInstrument) -> float | None:
    capi = _load_bronze(CapitalComOHLCVRestConnector.TABLE_NAME, inst.symbol)
    duka = _load_bronze(DukascopyOHLCVConnector.TABLE_NAME, inst.symbol)

    if capi is None and duka is None:
        print(f"[{inst.symbol}] no bronze data - skip")
        return None

    # Capital first, native scale - that's the canonical reference going forward.
    if capi is not None:
        print(f"[{inst.symbol}] capital bronze -> silver : {len(capi):,} bars (native)")
        merge.save_macro(clean_ohlcv(capi))

    if duka is None:
        return None

    if capi is None:
        print(f"[{inst.symbol}] dukascopy bronze -> silver : {len(duka):,} bars (no capital, unshifted)")
        merge.save_macro(clean_ohlcv(duka))
        return 0.0

    offset = _compute_offset(capi, duka)
    print(f"[{inst.symbol}] offset (capital - dukascopy, 1m median): {offset:+.6f}")
    shifted = _shift_prices(duka, offset)
    print(f"[{inst.symbol}] dukascopy bronze -> silver : {len(shifted):,} bars (shifted by offset)")
    merge.save_macro(clean_ohlcv(shifted))
    return offset


offsets = {}

for inst in MACRO_INSTRUMENTS:
    try:
        offset = _build(inst)
        if offset is not None:
            offsets[inst.symbol] = offset
    except Exception as e:
        print(f"[{inst.symbol}] ERROR: {e}")

OFFSETS_FILE.parent.mkdir(parents=True, exist_ok=True)
OFFSETS_FILE.write_text(json.dumps(offsets, indent=2))
print(f"\nOffsets saved to {OFFSETS_FILE}")
