"""End of v0.6.2 - Open-Meteo raw archive output, no connector.

Shows what Open-Meteo /v1/archive returns: a `daily` struct with
parallel arrays for time, temperature_2m_max, etc. (column-oriented,
not row-oriented).

"""
import json

import httpx

URL = "https://archive-api.open-meteo.com/v1/archive"

params = {
    "latitude":  38.5,
    "longitude": -98.0,
    "start_date": "2026-04-01",
    "end_date":   "2026-04-10",
    "daily":     "temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max",
    "timezone":  "UTC",
}

resp = httpx.get(URL, params=params, timeout=30)
resp.raise_for_status()
print(json.dumps(resp.json(), indent=2)[:1200])
