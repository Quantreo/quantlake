from datetime import datetime
import httpx
import polars as pl
from quantlake.bronze.base import HistoricalConnector
from quantlake.helper import to_utc, empty_ohlcv_df


class BinanceSpotOHLCVRestConnector(HistoricalConnector):
    TABLE_NAME = "binance_spot_ohlcv"
    _BASE_URL = "https://api.binance.com/api/v3/klines"
    _LIMIT = 1000

    def __init__(self, timeframe: str = "1m"):
        self.timeframe = timeframe

    def fetch(self, symbol: str, start: datetime, end: datetime) -> pl.DataFrame:
        start_ms = int(to_utc(start).timestamp() * 1000)
        end_ms = int(to_utc(end).timestamp() * 1000)

        rows = []
        current_ms = start_ms

        with httpx.Client(timeout=30) as client:
            while current_ms < end_ms:
                resp = client.get(self._BASE_URL, params={
                    "symbol": symbol,
                    "interval": self.timeframe,
                    "startTime": current_ms,
                    "endTime": end_ms,
                    "limit": self._LIMIT,
                })
                resp.raise_for_status()
                batch = resp.json()

                if not batch:
                    break

                rows.extend(batch)
                current_ms = batch[-1][0] + 1

        if not rows:
            return empty_ohlcv_df()

        return pl.DataFrame({
            "timestamp": pl.Series([r[0] for r in rows], dtype=pl.Int64),
            "timestamp_close": pl.Series([r[6] for r in rows], dtype=pl.Int64),
            "open": pl.Series([float(r[1]) for r in rows], dtype=pl.Float64),
            "high": pl.Series([float(r[2]) for r in rows], dtype=pl.Float64),
            "low": pl.Series([float(r[3]) for r in rows], dtype=pl.Float64),
            "close": pl.Series([float(r[4]) for r in rows], dtype=pl.Float64),
            "volume": pl.Series([float(r[5]) for r in rows], dtype=pl.Float64),
        }).with_columns(
            pl.from_epoch("timestamp", time_unit="ms").dt.replace_time_zone("UTC").cast(pl.Datetime("us", "UTC")),
            pl.from_epoch("timestamp_close", time_unit="ms").dt.replace_time_zone("UTC").cast(pl.Datetime("us", "UTC")),
        )
