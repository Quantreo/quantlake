"""End of video 1.2 — first connector.

A single self-contained script that paginates Binance REST and prints
the first/last bars. No library, no Delta storage. Just URL → JSON →
DataFrame → print.
"""
import httpx
from datetime import datetime, UTC
import polars as pl
from quantlake.config import BRONZE_ROOT
from quantlake.storage import upsert


def fetch_klines(symbol, start, end, interval="1m"):
    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)

    rows = []
    current_ms = start_ms

    with httpx.Client(timeout=30) as client:
        while current_ms < end_ms:
            resp = client.get(
                "https://api.binance.com/api/v3/klines",
                params={
                    "symbol": symbol,
                    "interval": interval,
                    "startTime": current_ms,
                    "endTime": end_ms,
                    "limit": 1000,
                },
            )
            resp.raise_for_status()
            batch = resp.json()
            if not batch:
                break
            rows.extend(batch)
            current_ms = batch[-1][0] + 1

    if not rows:
        return pl.DataFrame()

    return pl.DataFrame({
        "timestamp": [r[0] for r in rows],
        "open":      [float(r[1]) for r in rows],
        "high":      [float(r[2]) for r in rows],
        "low":       [float(r[3]) for r in rows],
        "close":     [float(r[4]) for r in rows],
        "volume":    [float(r[5]) for r in rows],
    }).with_columns(
        pl.from_epoch("timestamp", time_unit="ms")
          .dt.replace_time_zone("UTC")
          .cast(pl.Datetime("us", "UTC"))
    )


df = fetch_klines("BTCUSDT", datetime(2025, 2, 17, tzinfo=UTC),
                  datetime(2025, 2, 18, tzinfo=UTC))

df = df.with_columns(
    pl.lit("BTCUSDT").alias("symbol"),
    pl.col("timestamp").dt.year().cast(pl.Int32).alias("year"),
    pl.col("timestamp").dt.month().cast(pl.Int8).alias("month"),
)

print(f"{BRONZE_ROOT}/test_table")

upsert(df, f"{BRONZE_ROOT}/test_table")


