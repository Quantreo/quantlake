"""Quick look at Capital.com's raw REST output.

No connector, no parsing, no DataFrame. Just login, one /prices call
on EURUSD, pretty-print the JSON. Useful right before the connector
section to show what we're going to parse.

Run:
    poetry run python examples/bronze/capital_raw.py
"""
import json
import os
from datetime import datetime, timedelta, timezone

import httpx
from dotenv import load_dotenv

load_dotenv()

BASE = "https://demo-api-capital.backend-capital.com"

# 1. Login - tokens come back in response headers, not body.
login = httpx.post(
    f"{BASE}/api/v1/session",
    headers={"X-CAP-API-KEY": os.environ["CAPITAL_API_KEY"]},
    json={
        "identifier": os.environ["CAPITAL_LOGIN"],
        "password":   os.environ["CAPITAL_PASSWORD"],
        "encryptedPassword": False,
    },
)
login.raise_for_status()
cst = login.headers["CST"]
token = login.headers["X-SECURITY-TOKEN"]


# 2. One /prices call - last 3 minutes of EURUSD.
now = datetime.now(timezone.utc)
prices = httpx.get(
    f"{BASE}/api/v1/prices/EURUSD",
    headers={
        "X-CAP-API-KEY":    os.environ["CAPITAL_API_KEY"],
        "CST":              cst,
        "X-SECURITY-TOKEN": token,
    },
    params={
        "resolution": "MINUTE",
        "max":        10,
        "from":       (now - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%S"),
        "to":         now.strftime("%Y-%m-%dT%H:%M:%S"),
    },
)
prices.raise_for_status()

# 3. Pretty-print.
print(json.dumps(prices.json(), indent=2))









