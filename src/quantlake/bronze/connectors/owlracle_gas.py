"""End of v0.6.5 - Owlracle gas-price connector.

Two access modes:
  snapshot() - /gas endpoint, current state only. Use from a poll
               loop to build history at high frequency.
  fetch()    - /history endpoint, OHLC candles aggregated by Owlracle
               at a chosen timeframe (10m, 30m, 1h, ...).

Multi-chain (Ethereum, Polygon, Arbitrum, BSC, ...) - pick via the
network arg.

Requires OWL_API_KEY in .env (free tier covers both endpoints with
rate limits).

Columns returned by snapshot():
    timestamp, price (fastest maxFeePerGas in gwei),
    avg_gas, avg_time, avg_tx (network activity features).

Columns returned by fetch():
    timestamp, open, high, low, close (gas price OHLC in gwei),
    samples (tx count in the candle).
"""
import os
from datetime import datetime, timezone

import httpx
import polars as pl


class OwlracleGasConnector:
    TABLE_NAME = "owlracle_eth_gas"

    _SNAPSHOT_URL = "https://api.owlracle.info/v4/{network}/gas"
    _HISTORY_URL  = "https://api.owlracle.info/v4/{network}/history"

    def __init__(self, network: str = "eth", api_key: str | None = None):
        self.network = network
        self.api_key = api_key or os.getenv("OWL_API_KEY")
        if not self.api_key:
            raise ValueError("OWL_API_KEY missing - set it in .env")

    def snapshot(self) -> pl.DataFrame:
        """Fetch the current gas snapshot. Single-row DataFrame."""
        url = self._SNAPSHOT_URL.format(network=self.network)
        with httpx.Client(timeout=15) as client:
            resp = client.get(url, headers={"X-API-KEY": self.api_key})
            resp.raise_for_status()
        payload = resp.json()

        ts_raw = payload.get("timestamp")
        ts = (
            datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            if ts_raw else datetime.now(tz=None).astimezone()
        )

        speeds = payload.get("speeds") or []
        price = float(speeds[0]["maxFeePerGas"]) if speeds else float("nan")

        return pl.DataFrame({
            "timestamp": pl.Series([ts],                                   dtype=pl.Datetime("us", "UTC")),
            "price":     pl.Series([price],                                dtype=pl.Float64),
            "avg_gas":   pl.Series([float(payload.get("avgGas")  or 0.0)], dtype=pl.Float64),
            "avg_time":  pl.Series([float(payload.get("avgTime") or 0.0)], dtype=pl.Float64),
            "avg_tx":    pl.Series([float(payload.get("avgTx")   or 0.0)], dtype=pl.Float64),
        })

    def fetch(self, timeframe: int = 10, candles: int = 1000) -> pl.DataFrame:
        """Fetch historical OHLC gas-price candles.

        Args:
            timeframe: candle size in minutes (e.g. 10 for 10-min candles).
            candles: number of candles to return, max 1000 per call.
        """
        url = self._HISTORY_URL.format(network=self.network)
        params = {"timeframe": timeframe, "candles": candles}
        with httpx.Client(timeout=30) as client:
            resp = client.get(url, params=params, headers={"X-API-KEY": self.api_key})
            resp.raise_for_status()
        payload = resp.json()

        rows = payload.get("candles") or []
        if not rows:
            return _empty_history_df()

        return pl.DataFrame({
            "timestamp": [_parse_ts(r.get("timestamp")) for r in rows],
            "open":      [float(r["gasPrice"]["open"])  for r in rows],
            "high":      [float(r["gasPrice"]["high"])  for r in rows],
            "low":       [float(r["gasPrice"]["low"])   for r in rows],
            "close":     [float(r["gasPrice"]["close"]) for r in rows],
            "samples":   [int(r.get("samples") or 0)    for r in rows],
        }).with_columns(pl.col("timestamp").cast(pl.Datetime("us", "UTC"))).sort("timestamp")


def _parse_ts(ts_raw) -> datetime:
    if ts_raw is None:
        return datetime.now(tz=timezone.utc)
    if isinstance(ts_raw, (int, float)):
        return datetime.fromtimestamp(ts_raw, tz=timezone.utc)
    return datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))


def _empty_history_df() -> pl.DataFrame:
    return pl.DataFrame(schema={
        "timestamp": pl.Datetime("us", "UTC"),
        "open":      pl.Float64,
        "high":      pl.Float64,
        "low":       pl.Float64,
        "close":     pl.Float64,
        "samples":   pl.Int64,
    })
