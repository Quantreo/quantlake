"""End of v0.6.3 - USDA NASS QuickStats connector.

Pulls annual planted acreage at state granularity. Doesn't fit the
HistoricalConnector(symbol, start, end) shape - the natural grain is
(commodity, class_desc, states, year_range). We expose fetch_planted
instead.

Each row is stamped at the approximate report release date (e.g.
Winter Wheat Seedings ~Jan 12) so backtests don't leak future-known
acreage.

Requires NASS_API_KEY in .env.

Columns returned: timestamp, state, year, commodity, class_desc, planted_acres.
"""
import os
from datetime import datetime, timezone

import httpx
import polars as pl

_QUICKSTATS_URL = "https://quickstats.nass.usda.gov/api/api_GET/"

# Approximate release date by (commodity, class_desc).
_RELEASE_CALENDAR = {
    ("WHEAT", "WINTER"):                (1, 12),
    ("WHEAT", "SPRING, (EXCL DURUM)"):  (6, 30),
    ("WHEAT", "DURUM"):                 (6, 30),
    ("CORN",  "ALL"):                   (6, 30),
    ("SOYBEANS", "ALL"):                (6, 30),
}
_DEFAULT_RELEASE = (7, 1)


class USDANassConnector:
    TABLE_NAME = "usda_nass_planted"

    def __init__(self, api_key: str | None = None, timeout: float = 30.0):
        self.api_key = api_key or os.getenv("NASS_API_KEY")
        if not self.api_key:
            raise ValueError("NASS_API_KEY missing - set it in .env")
        self._timeout = timeout

    def fetch_planted(
        self,
        commodity: str,
        class_desc: str | None,
        states: list[str],
        year_start: int,
        year_end: int,
    ) -> pl.DataFrame:
        """Fetch annual planted acreage at state level.

        Args:
            commodity:  "WHEAT", "CORN", "SOYBEANS" (NASS uppercase).
            class_desc: e.g. "WINTER", "SPRING, (EXCL DURUM)", "ALL", or None.
            states:     USPS codes, e.g. ["KS", "OK", "TX"].
            year_start: inclusive.
            year_end:   inclusive.
        """
        params: dict = {
            "key":               self.api_key,
            "commodity_desc":    commodity,
            "statisticcat_desc": "AREA PLANTED",
            "agg_level_desc":    "STATE",
            "source_desc":       "SURVEY",
            "year__GE":          year_start,
            "year__LE":          year_end,
            "format":            "JSON",
            "unit_desc":         "ACRES",
            "state_alpha":       states,
        }
        if class_desc is not None:
            params["class_desc"] = class_desc

        with httpx.Client(timeout=self._timeout) as client:
            resp = client.get(_QUICKSTATS_URL, params=params)
            resp.raise_for_status()
            payload = resp.json()

        rows = payload.get("data") or []
        # Drop monthly progress rows; keep annual rollups only.
        parsed = [
            _parse_row(r, commodity)
            for r in rows
            if r.get("reference_period_desc") == "YEAR"
        ]
        parsed = [p for p in parsed if p is not None]
        if not parsed:
            return _empty_df()

        return pl.DataFrame(parsed).with_columns(
            pl.col("timestamp").cast(pl.Datetime("us", "UTC")),
            pl.col("year").cast(pl.Int32),
            pl.col("planted_acres").cast(pl.Float64),
        ).sort(["state", "year"])


def _release_timestamp(commodity: str, class_desc: str, year: int) -> datetime:
    """Approximate UTC time at which NASS published the figure."""
    key = (commodity.upper(), class_desc.upper())
    month, day = _RELEASE_CALENDAR.get(key, _DEFAULT_RELEASE)
    return datetime(year, month, day, 16, 0, tzinfo=timezone.utc)


def _parse_row(r: dict, commodity: str) -> dict | None:
    raw = r.get("Value")
    if raw is None:
        return None
    value = _parse_value(raw)
    try:
        year = int(r.get("year"))
    except (TypeError, ValueError):
        return None
    class_desc = (r.get("class_desc") or "ALL").strip()
    state = r.get("state_alpha")
    if not state:
        return None

    return {
        "timestamp":     _release_timestamp(commodity, class_desc, year),
        "state":         state,
        "year":          year,
        "commodity":     commodity.upper(),
        "class_desc":    class_desc,
        "planted_acres": value,
    }


def _parse_value(raw: str) -> float:
    """NASS uses (D), (Z), (NA), (S) as suppression codes. Map to NaN."""
    if not isinstance(raw, str):
        return float("nan")
    s = raw.strip().replace(",", "")
    if s in ("", "(D)", "(Z)", "(NA)", "(S)"):
        return float("nan")
    try:
        return float(s)
    except ValueError:
        return float("nan")


def _empty_df() -> pl.DataFrame:
    return pl.DataFrame(schema={
        "timestamp":     pl.Datetime("us", "UTC"),
        "state":         pl.Utf8,
        "year":          pl.Int32,
        "commodity":     pl.Utf8,
        "class_desc":    pl.Utf8,
        "planted_acres": pl.Float64,
    })
