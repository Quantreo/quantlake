"""End of v0.6.5 - Owlracle raw output, no connector wrapper.

Two endpoints, two payload shapes:

  /gas      - current single-point snapshot. Fields: timestamp,
              speeds[] (priority tiers, [0] = fastest), avgGas,
              avgTime, avgTx.

  /history  - OHLC candles aggregated server-side at the requested
              timeframe (in minutes). Each candle has gasPrice
              (open/high/low/close in gwei), baseFee, txFee, and
              samples (tx count in the bucket).

Run:
    poetry run python examples/bronze/owl_raw.py
"""
import json
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

HEADERS = {"X-API-KEY": os.environ["OWL_API_KEY"]}


URL_HIST = "https://api.owlracle.info/v4/eth/history"
resp = httpx.get(URL_HIST, params={"timeframe": 10, "candles": 5}, headers=HEADERS, timeout=30)
resp.raise_for_status()
print("\n=== /history (10-min candles, last 5) ===")
print(json.dumps(resp.json(), indent=2)[:1500])