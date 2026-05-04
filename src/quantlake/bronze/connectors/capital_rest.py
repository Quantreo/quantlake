"""End of v0.5.1 — Capital.com REST OHLCV connector.

CST + X-SECURITY-TOKEN auth (tokens come from response headers, not body),
401-retry on token expiry, paginated /prices with a 95% window cap to
avoid Capital's invalid.max.daterange error.

Bid/ask are in the payload: open/high/low/close are mid (average of bid &
ask), spread_open/spread_close = (ask - bid) — same canonical schema as
the exchange connectors.
"""
import os
import time
from datetime import datetime, timedelta

import httpx
import polars as pl

from quantlake.bronze.base import HistoricalConnector
from quantlake.helper import empty_ohlcv_df, to_utc

# Capital.com resolution strings per canonical timeframe, with the duration in
# seconds — used to advance the pagination window past the last returned bar.
_INTERVAL_MAP: dict[str, tuple[str, int]] = {
    "1m":  ("MINUTE",         60),
    "5m":  ("MINUTE_5",      300),
    "15m": ("MINUTE_15",     900),
    "30m": ("MINUTE_30",    1800),
    "1h":  ("HOUR",         3600),
    "4h":  ("HOUR_4",      14400),
    "1d":  ("DAY",         86400),
    "1w":  ("WEEK",       604800),
}

_LIMIT = 1000            # Capital.com hard cap per /prices request
_DEMO_BASE = "https://demo-api-capital.backend-capital.com"
_LIVE_BASE = "https://api-capital.backend-capital.com"


class CapitalComOHLCVRestConnector(HistoricalConnector):
    """Fetches CFD/FX/index OHLCV from the Capital.com REST API.

    Auth: CST + X-SECURITY-TOKEN from /session (requires CAPITAL_API_KEY,
    CAPITAL_LOGIN, CAPITAL_PASSWORD in .env). Tokens expire after ~10 min of
    inactivity — refreshed lazily on 401.

    Bid/ask are in the payload: we keep `open/high/low/close` as mid
    (average of bid & ask) and expose `spread_open`, `spread_close` so the
    canonical schema stays compatible with exchange connectors.

    Columns returned: timestamp, open, high, low, close, volume,
    spread_open, spread_close.
    """

    TABLE_NAME = "capitalcom_ohlcv"

    def __init__(
        self,
        timeframe: str = "1m",
        demo: bool = True,
        api_key: str | None = None,
        login: str | None = None,
        password: str | None = None,
    ):
        if timeframe not in _INTERVAL_MAP:
            raise ValueError(f"Unsupported timeframe: {timeframe}. Supported: {list(_INTERVAL_MAP)}")
        self.timeframe = timeframe
        self._resolution, self._interval_sec = _INTERVAL_MAP[timeframe]
        self._base = _DEMO_BASE if demo else _LIVE_BASE

        self._api_key = api_key or os.getenv("CAPITAL_API_KEY")
        self._login = login or os.getenv("CAPITAL_LOGIN")
        self._password = password or os.getenv("CAPITAL_PASSWORD")
        if not (self._api_key and self._login and self._password):
            raise ValueError(
                "Missing Capital.com credentials - set CAPITAL_API_KEY, "
                "CAPITAL_LOGIN, CAPITAL_PASSWORD in .env or pass them explicitly."
            )

        self._cst: str | None = None
        self._security_token: str | None = None

    # auth
    def _login_session(self, client: httpx.Client) -> None:
        # Capital.com throttles session creation (HTTP 429). Backoff a few times
        # before giving up so a burst of connectors in the same process doesn't
        # fail hard.
        for attempt in range(4):
            resp = client.post(
                "/api/v1/session",
                headers={"X-CAP-API-KEY": self._api_key, "Content-Type": "application/json"},
                json={"identifier": self._login, "password": self._password, "encryptedPassword": False},
            )
            if resp.status_code == 429:
                time.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            self._cst = resp.headers["CST"]
            self._security_token = resp.headers["X-SECURITY-TOKEN"]
            return
        resp.raise_for_status()

    def _ensure_session(self, client: httpx.Client) -> None:
        if self._cst is None or self._security_token is None:
            self._login_session(client)

    def _auth_headers(self) -> dict:
        return {
            "X-CAP-API-KEY": self._api_key,
            "CST": self._cst or "",
            "X-SECURITY-TOKEN": self._security_token or "",
        }

    # fetch
    def fetch(self, symbol: str, start: datetime, end: datetime) -> pl.DataFrame:
        start_utc = to_utc(start)
        end_utc = to_utc(end)

        # Capital.com rejects windows >= max * interval with
        # `error.invalid.max.daterange`, so keep the window under the cap.
        # 95% gives a safety margin while still advancing in large chunks.
        window_sec = int(_LIMIT * self._interval_sec * 0.95)
        cursor = start_utc
        parts: list[pl.DataFrame] = []

        with httpx.Client(base_url=self._base, timeout=30) as client:
            self._ensure_session(client)

            while cursor < end_utc:
                window_end = min(cursor + timedelta(seconds=window_sec), end_utc)
                payload = self._fetch_window(client, symbol, cursor, window_end)
                rows = payload.get("prices", [])

                if not rows:
                    # Either we're past the epic's available history or we hit
                    # a weekend gap - jump forward a full window to keep
                    # progressing rather than looping on empty responses.
                    cursor = window_end
                    continue

                parts.append(_parse_prices(rows))
                last_ts = rows[-1]["snapshotTimeUTC"]
                cursor = _iso_to_datetime(last_ts) + timedelta(seconds=self._interval_sec)

        if not parts:
            return empty_ohlcv_df()

        return (
            pl.concat(parts)
            .unique(subset=["timestamp"])
            .filter(pl.col("timestamp").is_between(pl.lit(start_utc), pl.lit(end_utc)))
            .sort("timestamp")
        )

    def _fetch_window(self, client: httpx.Client, symbol: str, frm: datetime, to: datetime) -> dict:
        params = {
            "resolution": self._resolution,
            "max": _LIMIT,
            "from": frm.strftime("%Y-%m-%dT%H:%M:%S"),
            "to": to.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        resp = client.get(f"/api/v1/prices/{symbol}", headers=self._auth_headers(), params=params)

        if resp.status_code == 401:  # session expired -> re-login once and retry
            self._cst = self._security_token = None
            self._login_session(client)
            resp = client.get(f"/api/v1/prices/{symbol}", headers=self._auth_headers(), params=params)

        if resp.status_code == 404:
            return {"prices": []}  # no bars in this window (weekend, past epic history)

        if resp.status_code >= 400:
            raise RuntimeError(f"Capital.com /prices HTTP {resp.status_code}: {resp.text[:300]}")
        return resp.json()


# helpers

def _iso_to_datetime(s: str) -> datetime:
    """Capital.com returns 'YYYY-MM-DDTHH:MM:SS' (no tz suffix, UTC implied)."""
    from datetime import timezone
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def _parse_prices(rows: list[dict]) -> pl.DataFrame:
    """Build a DataFrame with canonical OHLCV (mid) + spread_open/close."""

    def mid(p: dict) -> float | None:
        b, a = p.get("bid"), p.get("ask")
        return (b + a) / 2 if b is not None and a is not None else (b if b is not None else a)

    def spread(p: dict) -> float | None:
        b, a = p.get("bid"), p.get("ask")
        return (a - b) if b is not None and a is not None else None

    return pl.DataFrame({
        "timestamp":       [_iso_to_datetime(r["snapshotTimeUTC"]) for r in rows],
        "open":            [mid(r["openPrice"])  for r in rows],
        "high":            [mid(r["highPrice"])  for r in rows],
        "low":             [mid(r["lowPrice"])   for r in rows],
        "close":           [mid(r["closePrice"]) for r in rows],
        "volume":          [float(r.get("lastTradedVolume") or 0) for r in rows],
        "spread_open":     [spread(r["openPrice"])  for r in rows],
        "spread_close":    [spread(r["closePrice"]) for r in rows],
    }).with_columns(pl.col("timestamp").cast(pl.Datetime("us", "UTC")))



