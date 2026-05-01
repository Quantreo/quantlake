"""End of video 3.1 — silver cleaning before/after demo.

A 4-row DataFrame with 4 deliberate problems:
  - row 0: open is None     → fill_null kicks in
  - row 1: high < low        → invalid_bar, all 4 prices become NaN
  - row 2: volume = -5       → negative volume, becomes NaN
  - row 3: high = inf        → is_infinite, becomes NaN, then high<low triggers, all prices NaN

Run this and compare "Dirty" vs "Cleaned" — every rule fires.
"""
from datetime import datetime, timezone

import polars as pl

from quantlake.silver.ohlcv import clean_ohlcv


def _ts(hour: int) -> datetime:
    return datetime(2025, 4, 1, hour, tzinfo=timezone.utc)

dirty = pl.DataFrame({
    "timestamp": pl.Series([_ts(0), _ts(1), _ts(2), _ts(3)], dtype=pl.Datetime("us", "UTC")),
    "open":      pl.Series([100.0,   None,   105.0,  102.0], dtype=pl.Float64),
    "high":      pl.Series([101.0,   102.0,   99.0,  float("inf")], dtype=pl.Float64),  # row 1: high < low
    "low":       pl.Series([ 99.0,   101.0,  104.0,  101.0], dtype=pl.Float64),         # row 2: high < low
    "close":     pl.Series([100.5,   101.5,  103.0,  101.5], dtype=pl.Float64),
    "volume":    pl.Series([  1.0,     1.0,   -5.0,    1.0], dtype=pl.Float64),         # row 2: volume < 0
})

print("=== Dirty input ===")
print(dirty)



clean = clean_ohlcv(dirty)

print("\n=== After clean_ohlcv ===")
print(clean)
