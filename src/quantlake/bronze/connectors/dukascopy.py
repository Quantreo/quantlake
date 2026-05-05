"""End of v0.5.3 - Dukascopy historical minute OHLCV connector.

Fetches bid + ask minute candles from Dukascopy's public datafeed
(https://datafeed.dukascopy.com), merges them into the canonical mid + spread
schema, and returns a single DataFrame.

Dukascopy publishes daily files per instrument in a lightly compressed binary
format (.bi5, LZMA). The URL pattern is:
    {BASE}/{INSTR}/{YYYY}/{MM-1:02d}/{DD:02d}/BID_candles_min_1.bi5
(the month is 0-indexed, classic gotcha)

Each file holds exactly 1440 records of 24 bytes:
    >IIIIIf = t_sec_from_day_start, open*scale, close*scale, low*scale, high*scale, volume

FX pairs use a *1e5 scale (5 decimals); metals and indices use *1e3 (3 decimals).
"""
import lzma
import struct
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import polars as pl

from quantlake.bronze.base import HistoricalConnector
from quantlake.helper import empty_ohlcv_df, to_utc

_BASE = "https://datafeed.dukascopy.com/datafeed"
_RECORD = struct.Struct(">IIIIIf")
_DROP_ZERO_VOLUME = False


class DukascopyOHLCVConnector(HistoricalConnector):
    """Fetches 1-minute OHLCV from the Dukascopy public datafeed."""

    TABLE_NAME = "dukascopy_ohlcv"

    def __init__(self, price_scale: float = 100_000.0, max_workers: int = 3):
        self.price_scale = price_scale
        self.max_workers = max_workers

    def fetch(self, symbol: str, start: datetime, end: datetime) -> pl.DataFrame:
        start_d = to_utc(start).date()
        end_d = to_utc(end).date()
        days = [start_d + timedelta(days=i) for i in range((end_d - start_d).days + 1)]
        days = [d for d in days if d.weekday() != 5]  # FX closed Saturdays

        parts: list[pl.DataFrame] = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as ex:
            futs = {ex.submit(self._fetch_day, symbol, d): d for d in days}
            for fut in as_completed(futs):
                df = fut.result()
                if df is not None and not df.is_empty():
                    parts.append(df)

        if not parts:
            return empty_ohlcv_df()

        start_utc = to_utc(start)
        end_utc = to_utc(end)
        return (
            pl.concat(parts, how="diagonal")
            .unique(subset=["timestamp"])
            .filter(pl.col("timestamp").is_between(pl.lit(start_utc), pl.lit(end_utc)))
            .sort("timestamp")
        )

    def _fetch_day(self, symbol: str, d: date) -> Optional[pl.DataFrame]:
        bid_blob = _fetch_bi5(_url(symbol, d, "BID"))
        ask_blob = _fetch_bi5(_url(symbol, d, "ASK"))
        if bid_blob is None or ask_blob is None:
            return None

        bid = _parse_candles(bid_blob, d, self.price_scale).rename({
            "open": "o_b", "high": "h_b", "low": "l_b", "close": "c_b", "volume": "v_b",
        })
        ask = _parse_candles(ask_blob, d, self.price_scale).rename({
            "open": "o_a", "high": "h_a", "low": "l_a", "close": "c_a", "volume": "v_a",
        })
        if bid.is_empty() or ask.is_empty():
            return None

        return bid.join(ask, on="timestamp", how="inner").select(
            pl.col("timestamp"),
            ((pl.col("o_b") + pl.col("o_a")) / 2).alias("open"),
            ((pl.col("h_b") + pl.col("h_a")) / 2).alias("high"),
            ((pl.col("l_b") + pl.col("l_a")) / 2).alias("low"),
            ((pl.col("c_b") + pl.col("c_a")) / 2).alias("close"),
            (pl.col("v_b") + pl.col("v_a")).alias("volume"),
            (pl.col("o_a") - pl.col("o_b")).alias("spread_open"),
            (pl.col("c_a") - pl.col("c_b")).alias("spread_close"),
        )


def _url(instrument: str, d: date, side: str) -> str:
    # Note: Dukascopy uses 0-indexed months in URL paths.
    return f"{_BASE}/{instrument}/{d.year:04d}/{d.month - 1:02d}/{d.day:02d}/{side}_candles_min_1.bi5"


def _fetch_bi5(url: str) -> Optional[bytes]:
    """Download and decompress one .bi5. Returns None on 404 (weekend/holiday)."""
    for attempt in range(5):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                raw = r.read()
            break
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code in (503, 429):
                time.sleep(1 + attempt * 2)
                continue
            raise
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
            time.sleep(1 + attempt * 2)
            continue
    else:
        raise RuntimeError(f"Gave up on {url} after retries")

    if not raw:
        return None
    return lzma.decompress(raw, format=lzma.FORMAT_AUTO)


def _parse_candles(blob: bytes, day: date, price_scale: float) -> pl.DataFrame:
    n = len(blob) // _RECORD.size
    day_start_s = int(datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp())

    ts, op, hi, lo, cl, vo = [], [], [], [], [], []
    for i in range(n):
        t, o, c, l, h, v = _RECORD.unpack_from(blob, i * _RECORD.size)
        if _DROP_ZERO_VOLUME and v == 0.0:
            continue
        ts.append(day_start_s + t)
        op.append(o / price_scale); hi.append(h / price_scale)
        lo.append(l / price_scale); cl.append(c / price_scale); vo.append(v)

    return pl.DataFrame({
        "timestamp": ts, "open": op, "high": hi, "low": lo, "close": cl, "volume": vo,
    }).with_columns(pl.from_epoch("timestamp", time_unit="s").dt.replace_time_zone("UTC"))
