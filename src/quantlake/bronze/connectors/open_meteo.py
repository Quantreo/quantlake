"""End of v0.6.2 - Open-Meteo connector. Free, no API key.

Two access modes, same normalized schema:

  fetch()    - /v1/archive (ECMWF ERA5 reanalysis). Deep daily history
               from 1940 onwards. Used by the historical bootstrap.
  snapshot() - /v1/forecast with past_days / forecast_days. Recent
               history + forecast for the live poll loop.

Symbol convention: caller passes a geographical key (e.g. US state
code "KS") used as the bronze partition. The connector takes
latitude/longitude separately at __init__ - the symbol does NOT need
to be a name the API recognizes.

Columns returned (daily granularity):
    timestamp, temp_max, temp_min, precip, wind_speed_max
"""
import time
from datetime import datetime, timedelta, timezone

import httpx
import polars as pl

from quantlake.bronze.base import HistoricalConnector
from quantlake.helper import to_utc

_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

_ARCHIVE_CHUNK_DAYS = 10 * 365   # stay polite under the soft ceiling
_SLEEP_BETWEEN_CHUNKS_SEC = 1.0

_DAILY_VARS = (
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "wind_speed_10m_max",
)
_RENAME = {
    "temperature_2m_max": "temp_max",
    "temperature_2m_min": "temp_min",
    "precipitation_sum":  "precip",
    "wind_speed_10m_max": "wind_speed_max",
}


class OpenMeteoConnector(HistoricalConnector):

    TABLE_NAME = "open_meteo"

    def __init__(self, latitude: float, longitude: float, timeout: float = 30.0):
        self.latitude = latitude
        self.longitude = longitude
        self._timeout = timeout

    def fetch(self, symbol: str, start: datetime, end: datetime) -> pl.DataFrame:
        """Fetch daily aggregates between start and end. Symbol is a
        partition key for downstream, the API itself uses lat/lon.
        """
        start_utc, end_utc = to_utc(start), to_utc(end)
        parts: list[pl.DataFrame] = []
        cur = start_utc
        while cur <= end_utc:
            chunk_end = min(cur + timedelta(days=_ARCHIVE_CHUNK_DAYS - 1), end_utc)
            params = {
                "latitude":   self.latitude,
                "longitude":  self.longitude,
                "start_date": cur.strftime("%Y-%m-%d"),
                "end_date":   chunk_end.strftime("%Y-%m-%d"),
                "daily":      ",".join(_DAILY_VARS),
                "timezone":   "UTC",
            }
            df = self._get_daily(_ARCHIVE_URL, params)
            if not df.is_empty():
                parts.append(df)
            cur = chunk_end + timedelta(days=1)
            time.sleep(_SLEEP_BETWEEN_CHUNKS_SEC)

        if not parts:
            return _empty_df()
        return pl.concat(parts).unique(subset=["timestamp"]).sort("timestamp")

    def snapshot(self, past_days: int = 2, forecast_days: int = 7) -> pl.DataFrame:
        """Daily aggregates around 'now'. Use from a poll loop to refresh
        recent days plus a short-term forecast.
        """
        params = {
            "latitude":      self.latitude,
            "longitude":     self.longitude,
            "daily":         ",".join(_DAILY_VARS),
            "timezone":      "UTC",
            "past_days":     past_days,
            "forecast_days": forecast_days,
        }
        return self._get_daily(_FORECAST_URL, params)

    def _get_daily(self, url: str, params: dict) -> pl.DataFrame:
        with httpx.Client(timeout=self._timeout) as client:
            resp = _get_with_retry(client, url, params)
            payload = resp.json()
        daily = payload.get("daily") or {}
        dates = daily.get("time") or []
        if not dates:
            return _empty_df()

        df = pl.DataFrame({
            "timestamp": [datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc) for d in dates],
            **{v: [_safe_float(x) for x in (daily.get(v) or [])] for v in _DAILY_VARS},
        }).with_columns(pl.col("timestamp").cast(pl.Datetime("us", "UTC")))

        return df.rename({k: v for k, v in _RENAME.items() if k in df.columns}).sort("timestamp")


def _empty_df() -> pl.DataFrame:
    return pl.DataFrame(schema={
        "timestamp":      pl.Datetime("us", "UTC"),
        "temp_max":       pl.Float64,
        "temp_min":       pl.Float64,
        "precip":         pl.Float64,
        "wind_speed_max": pl.Float64,
    })


def _safe_float(v) -> float:
    if v is None:
        return float("nan")
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


def _get_with_retry(
    client: httpx.Client,
    url: str,
    params: dict,
    max_attempts: int = 5,
) -> httpx.Response:
    """GET with exponential backoff on 429 / 5xx.

    Open-Meteo free tier returns 429 under burst (600 calls/min limit
    or transient pressure). A few well-spaced retries usually succeed.
    Honors Retry-After if the server sets it.
    """
    backoff = 2.0
    for attempt in range(1, max_attempts + 1):
        resp = client.get(url, params=params)
        if resp.status_code == 429 and attempt < max_attempts:
            wait = float(resp.headers.get("Retry-After") or backoff)
            time.sleep(wait)
            backoff *= 2
            continue
        if 500 <= resp.status_code < 600 and attempt < max_attempts:
            time.sleep(backoff)
            backoff *= 2
            continue
        resp.raise_for_status()
        return resp
    resp.raise_for_status()
    return resp
