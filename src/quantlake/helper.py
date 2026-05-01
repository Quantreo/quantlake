from datetime import datetime, timezone

import polars as pl


TF_SECONDS = {
    "1m": 60,    "3m": 180,   "5m": 300,   "15m": 900,
    "30m": 1800, "1h": 3600,  "4h": 14400, "1d": 86400,
}


def to_utc(dt: datetime) -> datetime:
    """Normalize a datetime to UTC.

    Naive datetimes are assumed to represent UTC.
    Timezone-aware datetimes are properly converted (the wall-clock values are adjusted).
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def empty_ohlcv_df() -> pl.DataFrame:
    """Return an empty DataFrame with the canonical OHLCV schema.

    Use this when a connector fetches no data, to preserve a stable return type.
    """
    return pl.DataFrame({
        "timestamp":       pl.Series([], dtype=pl.Datetime("us", "UTC")),
        "timestamp_close": pl.Series([], dtype=pl.Datetime("us", "UTC")),
        "open":            pl.Series([], dtype=pl.Float64),
        "high":            pl.Series([], dtype=pl.Float64),
        "low":             pl.Series([], dtype=pl.Float64),
        "close":           pl.Series([], dtype=pl.Float64),
        "volume":          pl.Series([], dtype=pl.Float64),
    })
