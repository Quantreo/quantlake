"""Mini demo for video 2.1 - bulk archive in 25 lines, no class, no library.

Run this AT THE START of video 2.1 to show the elve what bulk is, before
writing the proper class. The point is: "look, in 25 lines we just got a
whole month of BTCUSDT data. Now let's wrap this into something
professional."
"""
import io
import zipfile

import httpx
import polars as pl

# ─── 1. Build the URL for one month ──────────────────────────────────────────
url = "https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2024-01.zip"

# ─── 2. Download the ZIP ─────────────────────────────────────────────────────
resp = httpx.get(url, timeout=60)
resp.raise_for_status()
print(f"Downloaded {len(resp.content):,} bytes")

# ─── 3. Unzip in memory and read the CSV ─────────────────────────────────────
with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
    csv_name = zf.namelist()[0]              # the single file inside the ZIP
    with zf.open(csv_name) as f:
        df = pl.read_csv(
            f.read(),
            has_header=False,                # Binance archives have no header
            new_columns=["timestamp", "open", "high", "low", "close", "volume",
                         "close_time", "quote_volume", "trades",
                         "taker_buy_volume", "taker_buy_quote_volume", "ignore"],
        )

# ─── 4. Look at it ───────────────────────────────────────────────────────────
print(df.head())
print(f"\nRows: {len(df):,}")
print(f"Schema: {df.schema}")
