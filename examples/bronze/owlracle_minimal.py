"""End of v0.6.5 - Quick look at the Owlracle connector.

Two demos in one file:
  1) snapshot() - current single-point gas reading.
  2) fetch()    - historical 10-minute OHLC candles.

Run:
    poetry run python examples/bronze/owlracle_minimal.py
"""
from quantlake.bronze.connectors.owlracle_gas import OwlracleGasConnector
from dotenv import load_dotenv

load_dotenv()


connector = OwlracleGasConnector(network="eth")

# 1) live snapshot
snap = connector.snapshot()
print("=== snapshot ===")
print(snap)

# 2) historical 10-min candles
hist = connector.fetch(timeframe=10, candles=200)
print("\n=== history (10-min candles) ===")
print(hist)
print(hist.schema)
