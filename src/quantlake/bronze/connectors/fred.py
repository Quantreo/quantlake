"""End of v0.6.1 - FRED REST connector.

Fetches macroeconomic time series from St. Louis Fed's public API.
Series identified by FRED ID ("DFF" = Fed Funds Rate, "DGS10" =
10-Year Treasury Yield, etc.).

Each observation carries a date but no release time. Naively stamping
"2026-04-21" as UTC midnight introduces a look-ahead bias up to ~21h:
H.15 rates for April 21 aren't published until 16:30 ET that day. The
connector accepts release_time_et (a wall-clock time in US Eastern,
DST-aware via zoneinfo) and converts each observation timestamp to
UTC correctly for both EDT and EST.

Requires FRED_API_KEY in .env.

Columns returned: timestamp (release time in UTC), value.
"""
import os
from datetime import datetime

import httpx
import polars as pl

from quantlake.bronze.base import HistoricalConnector
from quantlake.helper import to_utc


class FREDConnector(HistoricalConnector):

    TABLE_NAME = "fred"
    _BASE_URL = "https://api.stlouisfed.org/fred/series/observations"

    def __init__(self, api_key: str | None = None, release_time_et: str = "16:30"):
        self.api_key = api_key or os.getenv("FRED_API_KEY")
        if not self.api_key:
            raise ValueError("FRED_API_KEY missing - set it in .env")
        # Validate format early.
        datetime.strptime(release_time_et, "%H:%M")
        self.release_time_et = release_time_et

    def fetch(self, symbol: str, start: datetime, end: datetime) -> pl.DataFrame:
        params = {
            "series_id":         symbol,
            "api_key":           self.api_key,
            "file_type":         "json",
            "observation_start": to_utc(start).strftime("%Y-%m-%d"),
            "observation_end":   to_utc(end).strftime("%Y-%m-%d"),
        }
        with httpx.Client(timeout=30) as client:
            resp = client.get(self._BASE_URL, params=params)
            resp.raise_for_status()
            payload = resp.json()

        obs = payload.get("observations", [])
        if not obs:
            return pl.DataFrame(schema={
                "timestamp": pl.Datetime("us", "UTC"),
                "value":     pl.Float64,
            })

        # "YYYY-MM-DD HH:MM" parsed in US Eastern via zoneinfo (DST-aware)
        # then converted to UTC -> correct release time stamp.
        rt = self.release_time_et
        return pl.DataFrame({
            "timestamp": [f"{o['date']} {rt}" for o in obs],
            "value":     [_safe_float(o["value"]) for o in obs],
        }).with_columns(
            pl.col("timestamp")
            .str.to_datetime(format="%Y-%m-%d %H:%M", time_zone="America/New_York")
            .dt.convert_time_zone("UTC")
            .cast(pl.Datetime("us", "UTC"))
        ).sort("timestamp")


def _safe_float(v: str) -> float:
    if v in (".", "", None):
        return float("nan")
    return float(v)
