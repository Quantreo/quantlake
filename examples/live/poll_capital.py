"""End of v0.5.2 - poll.run on a real REST source.

Each minute boundary (+ 500 ms), fetch the last 5 minutes of EURUSD
from Capital and print the most recent closed bar. No bronze, no
silver, no gold - just the polling primitive + the connector. The
full bronze/silver/gold chain comes in v0.5.4.

Run:
    poetry run python examples/live/poll_capital.py
"""
from datetime import datetime, timedelta, timezone

import quantlake.poll as poll
from quantlake.bronze.connectors.capital_rest import CapitalComOHLCVRestConnector
from dotenv import load_dotenv

load_dotenv()

capital = CapitalComOHLCVRestConnector(timeframe="1m")


def fetch_eurusd():
    now = datetime.now(timezone.utc)
    df = capital.fetch(symbol="EURUSD", start=now - timedelta(minutes=5), end=now)
    if df.is_empty():
        print("no bars yet")
        return
    print(df.tail(1))


poll.run(fetch_eurusd, interval="1m", offset_ms=500)
