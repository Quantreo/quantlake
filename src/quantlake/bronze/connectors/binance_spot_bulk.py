import io
import zipfile
from datetime import datetime

import httpx
import polars as pl

from quantlake.bronze.base import HistoricalConnector
from quantlake.helper import empty_ohlcv_df, to_utc


class BinanceSpotOHLCVBulkConnector(HistoricalConnector):
    """Fetches spot OHLCV from Binance public S3 bucket (no API key, no rate limit).

    Downloads monthly ZIP files and returns a single concatenated DataFrame.
    Columns returned: timestamp, open, high, low, close, volume
    """

    TABLE_NAME = "binance_spot_ohlcv"
    _BASE_URL = "https://data.binance.vision/data/spot/monthly/klines"

    def __init__(self, timeframe: str = "1m"):
        self.timeframe = timeframe

    def fetch(self, symbol: str, start: datetime, end: datetime) -> pl.DataFrame:
        start_utc = to_utc(start)
        end_utc = to_utc(end)
        months = _month_range(start_utc, end_utc)
        parts = []

        with httpx.Client(timeout=60) as client:
            for year, month in months:
                url = f"{self._BASE_URL}/{symbol}/{self.timeframe}/{symbol}-{self.timeframe}-{year}-{month:02d}.zip"
                resp = client.get(url)
                if resp.status_code == 404:
                    continue  # symbol not listed yet for this month
                resp.raise_for_status()

                with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                    csv_name = zf.namelist()[0]
                    with zf.open(csv_name) as f:
                        df = pl.read_csv(
                            f.read(),
                            has_header=False,
                            new_columns=["timestamp", "open", "high", "low", "close", "volume",
                                         "close_time", "quote_volume", "trades",
                                         "taker_buy_volume", "taker_buy_quote_volume", "ignore"],
                        )
                # Binance changed timestamp unit over time: old files use ms (13 digits), recent use us (16 digits)
                time_unit = "us" if df["timestamp"].max() > 10 ** 15 else "ms"
                df = (
                    df.select(["timestamp", "close_time", "open", "high", "low", "close", "volume"])
                    .rename({"close_time": "timestamp_close"})
                    .with_columns(
                        pl.from_epoch("timestamp", time_unit=time_unit).dt.replace_time_zone("UTC").cast(
                            pl.Datetime("us", "UTC")),
                        pl.from_epoch("timestamp_close", time_unit=time_unit).dt.replace_time_zone("UTC").cast(
                            pl.Datetime("us", "UTC")),
                    )
                )
                parts.append(df)

        if not parts:
            return empty_ohlcv_df()

        return (
            pl.concat(parts)
            .filter(pl.col("timestamp").is_between(pl.lit(start_utc), pl.lit(end_utc)))
            .sort("timestamp")
        )


def _month_range(start: datetime, end: datetime) -> list[tuple[int, int]]:
    months = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        months.append((year, month))
        month += 1
        if month > 12:
            month = 1
            year += 1
    return months
