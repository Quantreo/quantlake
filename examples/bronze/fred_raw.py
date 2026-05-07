"""End of v0.6.1 - FRED raw REST output, no connector.

Shows what FRED returns: an `observations` array of {date, value}
where date is YYYY-MM-DD (no time of day) and value is a string with
"." for non-publication days.

Run:
    poetry run python examples/bronze/fred_raw.py
"""
import json
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

URL = "https://api.stlouisfed.org/fred/series/observations"
SERIES = "DGS10"   # 10-Year Treasury Yield

resp = httpx.get(URL, params={
    "series_id": SERIES,
    "api_key": os.environ["FRED_API_KEY"],
    "file_type": "json",
    "observation_start": "2026-04-01",
    "observation_end": "2026-04-15",
}, timeout=30)
resp.raise_for_status()

print(json.dumps(resp.json(), indent=2)[:1500])
